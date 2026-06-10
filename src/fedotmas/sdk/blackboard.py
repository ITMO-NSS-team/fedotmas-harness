"""The blackboard surface: a thin helper for opportunistic, non-topological activation.

This is a peer of the flow arrows, not sugar over them: it expresses what arrows cannot, agents
that self-activate whenever the shared store satisfies their condition, in no order anyone wired.
A Rule pairs that condition with a step. The step is either code (`fn`) or, like the agent atom,
a prompt: `prompt` plus an optional `input` template rendered over the rule's input with store
tags as fallback, so a rule that reads several facts at once stays declarative. For the common
produce-once shape the condition is derived from reads and writes, so a linear rule needs no
trigger; write `when` only when the activation is genuinely opportunistic (several rules
contending on the same fact, conditions not reducible to a single read).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from fedotmas.adapters import as_agent
from fedotmas.engine.contract import Agent, Fact, Result, View
from fedotmas.engine.system import System
from fedotmas.sdk.atoms import LLM, _render

StepFn = Callable[[Any, View], Awaitable[Any]]
When = Callable[[View], bool]


@dataclass
class Rule:
    """One blackboard agent. When its condition holds, run the step and write the result to
    the `writes` fact; `reads` names the fact fed to the step as input (empty means none).
    The step is `fn` (code) or `prompt` (an LLM call over the seam; `input` is the template
    for what the model sees, `returns` its output type) -- exactly one of the two. `when`
    defaults to produce-once, fire when `reads` exists and `writes` does not yet, so a
    pipeline rule needs no trigger; supply `when` for opportunistic activation. `meta` rides
    along to the agent, e.g. an auction bid that a Policy reads back off
    `agent.describe().meta`. An LLM rule binds its backend via `llm` here or the default at
    blackboard().
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


def _produce_once(reads: str, writes: str) -> When:
    if reads:
        return lambda v: v.exists(reads) and not v.exists(writes)
    return lambda v: not v.exists(writes)


def _prompt_fn(rule: Rule, llm: LLM) -> StepFn:
    name, prompt, template, returns = rule.name, rule.prompt, rule.input, rule.returns
    assert prompt is not None

    async def step(value: Any, view: View) -> Any:
        content = _render(template, value, view, name) if template else value
        return await llm.complete(prompt, content, view, returns=returns)

    return step


def _rule_agent(rule: Rule, default_llm: LLM | None) -> Agent:
    if (rule.fn is None) == (rule.prompt is None):
        raise ValueError(
            f"rule {rule.name!r}: exactly one of fn= or prompt= is required"
        )
    if not rule.writes:
        raise ValueError(f"rule {rule.name!r}: writes= is required")
    if rule.fn is not None:
        fn = rule.fn
    else:
        llm = rule.llm or default_llm
        if llm is None:
            raise ValueError(
                f"rule {rule.name!r} has no llm bound: pass llm= on the rule or as the "
                "default at blackboard()"
            )
        fn = _prompt_fn(rule, llm)

    async def invoke(input: Any, view: View) -> Result:
        value = await fn(view.value(rule.reads) if rule.reads else None, view)
        return Result(writes=[Fact(tag=rule.writes, value=value)])

    trigger = rule.when or _produce_once(rule.reads, rule.writes)
    return as_agent(
        invoke, name=rule.name, reads=rule.reads, trigger=trigger, meta=rule.meta
    )


def blackboard(*rules: Rule, llm: LLM | None = None) -> System:
    """Assemble rules into a blackboard System: agents that self-activate when their condition
    holds, with no fixed topology. `llm` is the default backend for prompt rules that did not
    bind their own. Run the System directly on the engine, or wrap it with nest to drop the
    whole blackboard into a flow as one typed node.
    """
    return System([_rule_agent(r, llm) for r in rules])
