"""The blackboard surface: opportunistic, non-topological activation.

A rule is a node that activates itself: when its condition holds against the shared store, it
fires and posts its result as a fact. That is what arrows cannot express, agents firing in no
order anyone wired, and it makes this surface a peer of the flows, not sugar over them. The
step inside a rule is either code (`fn`) or, like the agent atom, a prompt: `prompt` plus an
optional `input` template rendered over the rule's input with store tags as fallback, so a
rule that reads several facts at once stays declarative. For the common produce-once shape
the condition is derived from reads and writes, so a linear rule needs no trigger; write
`when` only when the activation is genuinely opportunistic (several rules contending on the
same fact, conditions not reducible to a single read).

blackboard(...) assembles rules into a Board: run it with board.run(seed, goal=...), hand
board.system to an engine executor for full control, or wrap it with nest to drop the whole
board into a flow as one typed node.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from fedotmas.adapters import as_node
from fedotmas.engine.contract import Fact, Node, Result, View
from fedotmas.engine.executor import ReactiveExecutor
from fedotmas.engine.policy import Policy
from fedotmas.engine.store import Store
from fedotmas.engine.system import System
from fedotmas.engine.terminate import Budget, Goal, Terminate
from fedotmas.sdk._template import render
from fedotmas.sdk.atoms import LLM
from fedotmas.sdk.flow import FlowRun

StepFn = Callable[[Any, View], Awaitable[Any]]
When = Callable[[View], bool]


@dataclass
class Rule:
    """One self-activating blackboard node. When its condition holds, run the step and write
    the result to the `writes` fact; `reads` names the fact fed to the step as input (empty
    means none). The step is `fn` (code) or `prompt` (an LLM call over the seam; `input` is
    the template for what the model sees, `returns` its output type) -- exactly one of the
    two. `when` defaults to produce-once, fire when `reads` exists and `writes` does not yet,
    so a pipeline rule needs no trigger; supply `when` for opportunistic activation. `meta`
    rides along to the node, e.g. an auction bid that a Policy reads back off
    `node.describe().meta`. An LLM rule binds its backend via `llm` here or the default at
    blackboard(). Construct with the lowercase `rule(...)` for symmetry with the atom
    factories.
    """

    name: str
    fn: StepFn | None = None
    writes: str = ""
    reads: str = ""
    when: When | None = None
    meta: dict[str, Any] = field(default_factory=dict)
    prompt: str | None = None
    input: str | None = None
    returns: Any = str
    llm: LLM | None = None


rule = Rule


def _produce_once(reads: str, writes: str) -> When:
    if reads:
        return lambda v: v.exists(reads) and not v.exists(writes)
    return lambda v: not v.exists(writes)


def _prompt_fn(r: Rule, llm: LLM) -> StepFn:
    name, prompt, template, returns = r.name, r.prompt, r.input, r.returns
    assert prompt is not None

    async def step(value: Any, view: View) -> Any:
        content = render(template, value, view, name) if template else value
        return await llm.complete(prompt, content, view, returns=returns)

    return step


def _rule_node(r: Rule, default_llm: LLM | None) -> Node:
    if (r.fn is None) == (r.prompt is None):
        raise ValueError(f"rule {r.name!r}: exactly one of fn= or prompt= is required")
    if not r.writes:
        raise ValueError(f"rule {r.name!r}: writes= is required")
    if r.fn is not None:
        fn = r.fn
    else:
        llm = r.llm or default_llm
        if llm is None:
            raise ValueError(
                f"rule {r.name!r} has no llm bound: pass llm= on the rule or as the "
                "default at blackboard()"
            )
        fn = _prompt_fn(r, llm)

    async def invoke(input: Any, view: View) -> Result:
        value = await fn(view.value(r.reads) if r.reads else None, view)
        return Result(writes=[Fact(tag=r.writes, value=value)])

    trigger = r.when or _produce_once(r.reads, r.writes)
    return as_node(invoke, name=r.name, reads=r.reads, trigger=trigger, meta=r.meta)


@dataclass
class Board:
    """An assembled blackboard: the System plus a run surface symmetric with Flow.run. A
    board has no single typed output, so `run` takes the seed facts as a tag -> value dict
    and a `goal` tag to read the result back from; everything else (store, terminate,
    budget cap) is derived. `system` is the raw engine System for executor-level control,
    and what nest() picks up when a board becomes one node of a flow.
    """

    system: System

    async def run(
        self,
        seed: dict[str, Any],
        *,
        goal: str,
        budget: int | None = None,
        policy: Policy | None = None,
    ) -> FlowRun:
        terminate: Terminate = Goal(lambda v: v.exists(goal))
        if budget is not None:
            terminate = terminate | Budget(budget)
        run = await ReactiveExecutor().run(
            self.system,
            Store(),
            seed=[Fact(tag=tag, value=value) for tag, value in seed.items()],
            terminate=terminate,
            policy=policy,
        )
        return FlowRun(run, goal)


def blackboard(*rules: Rule, llm: LLM | None = None) -> Board:
    """Assemble rules into a Board: nodes that self-activate when their condition holds, with
    no fixed topology. `llm` is the default backend for prompt rules that did not bind their
    own. Run it with board.run(seed, goal=...), drop to board.system for the raw engine, or
    wrap the board with nest to make it one typed node of a flow.
    """
    return Board(System([_rule_node(r, llm) for r in rules]))
