"""The blackboard surface: opportunistic, non-topological activation.

A rule is a node that activates itself: when its condition holds against the shared store, it
fires and posts its result as a fact. That is what arrows cannot express, agents firing in no
order anyone wired, and it makes this surface a peer of the flows, not sugar over them. The
step inside a rule is either code (`fn`) or, like the agent atom, a prompt: `prompt` plus an
optional `input` template rendered over the rule's input with store tags as fallback, so a
rule that reads several facts at once stays declarative. For the common produce-once shape
the condition is derived from reads and writes, so a linear rule needs no trigger; write
`when` only when the activation is genuinely opportunistic (several rules contending on the
same fact, conditions not reducible to a single read). The declarative form of `when` is a
sequence of fact tags, all of which must exist, with a `!` prefix for must-not-exist; a
callable over the View is the escape hatch beyond presence tests.

Re-fire identity comes from the facts a rule names: the engine fires a rule at most once per
distinct set of facts matched by `reads` plus the positive `when` tags, so a new version of
any of them re-arms the rule. A rule with a callable `when` and no `reads` names no facts and
fires at most once per run.

blackboard(...) assembles rules into a Board: run it with board.run(seed, goal=...), stream
the trace with board.stream, hand board.system to an engine executor for full control, or
wrap it with nest to drop the whole board into a flow as one typed node.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from typing import Any, cast

from fedotmas.engine.contract import Fact, Node, Result, View
from fedotmas.engine.executor import ReactiveExecutor
from fedotmas.engine.node import as_node
from fedotmas.engine.policy import Policy
from fedotmas.engine.report import StepReport
from fedotmas.engine.store import Store
from fedotmas.engine.system import System
from fedotmas.engine.terminate import Budget, Goal, Terminate
from fedotmas.sdk._template import render
from fedotmas.sdk.atoms import LLM
from fedotmas.sdk.flow import Outcome

StepFn = Callable[[Any, View], Awaitable[Any]]
When = Callable[[View], bool]


@dataclass
class Rule:
    """One self-activating blackboard node. When its condition holds, run the step and write
    the result to the `writes` fact; `reads` names the fact fed to the step as input (empty
    means none). The step is `fn` (code) or `prompt` (an LLM call over the seam; `input` is
    the template for what the model sees, `returns` its output type) -- exactly one of the
    two. `when` defaults to produce-once, fire when `reads` exists and `writes` does not yet,
    so a pipeline rule needs no trigger; supply `when` for opportunistic activation, as a
    sequence of tags that must all exist (`"!tag"` for must-not-exist) or, past presence
    tests, a callable over the View. `meta` rides along to the node, e.g. an auction bid that
    a Policy reads back off `node.describe().meta`. An LLM rule binds its backend via `llm`
    here, or falls back to the board default, then the run default.
    """

    name: str
    fn: StepFn | None = None
    writes: str = ""
    reads: str = ""
    when: When | Sequence[str] | None = None
    meta: dict[str, Any] = field(default_factory=dict)
    prompt: str | None = None
    input: str | None = None
    returns: Any = str
    llm: LLM | None = None


def _produce_once(reads: str, writes: str) -> When:
    if reads:
        return lambda v: v.exists(reads) and not v.exists(writes)
    return lambda v: not v.exists(writes)


def _check(r: Rule) -> None:
    if (r.fn is None) == (r.prompt is None):
        raise ValueError(f"rule {r.name!r}: exactly one of fn= or prompt= is required")
    if not r.writes:
        raise ValueError(f"rule {r.name!r}: writes= is required")
    when = r.when
    if when is None or callable(when):
        return
    if isinstance(when, str) or not when or any(t in ("", "!") for t in when):
        raise ValueError(f"rule {r.name!r}: when= takes a sequence of non-empty tags")


def _as_when(r: Rule) -> tuple[When, list[str]]:
    """The rule's trigger plus the positive when tags, which join its re-fire identity."""
    when = r.when
    if when is None:
        return _produce_once(r.reads, r.writes), []
    if callable(when):
        return cast(When, when), []
    need = [t for t in when if not t.startswith("!")]
    veto = [t[1:] for t in when if t.startswith("!")]
    trigger = lambda v: (  # noqa: E731
        all(v.exists(t) for t in need) and not any(v.exists(t) for t in veto)
    )
    return trigger, need


def _identity(r: Rule, need: list[str]) -> str:
    """The reads the engine dedups re-fires on: the input fact plus the positive when tags."""
    tags = [r.reads] if r.reads else []
    tags += [t for t in need if t not in tags]
    return " ".join(tags)


def _prompt_fn(r: Rule, llm: LLM) -> StepFn:
    name, prompt, template, returns = r.name, r.prompt, r.input, r.returns
    assert prompt is not None

    async def step(value: Any, view: View) -> Any:
        content = render(template, value, view, name) if template else value
        return await llm.complete(prompt, content, view, returns=returns)

    return step


def _rule_node(r: Rule, default_llm: LLM | None) -> Node:
    if r.fn is not None:
        fn = r.fn
    else:
        llm = r.llm or default_llm
        if llm is None:
            raise ValueError(
                f"rule {r.name!r} has no llm bound: pass llm= on the rule, as the "
                "default at blackboard(), or at run"
            )
        fn = _prompt_fn(r, llm)

    async def invoke(input: Any, view: View) -> Result:
        value = await fn(view.value(r.reads) if r.reads else None, view)
        return Result(writes=[Fact(tag=r.writes, value=value)])

    trigger, need = _as_when(r)
    return as_node(
        invoke, name=r.name, reads=_identity(r, need), trigger=trigger, meta=r.meta
    )


@dataclass
class Board:
    """An assembled blackboard: the rules plus a run surface symmetric with Flow.run. A board
    has no single typed output, so `run` takes the seed facts as a tag -> value dict and a
    `goal` tag to read the result back from; everything else (store, terminate, budget cap)
    is derived. `stream` is the same run yielded step by step. `compile` produces the engine
    System (`system` is its no-argument form), for executor-level control and for what nest()
    picks up when a board becomes one node of a flow.
    """

    rules: tuple[Rule, ...]
    llm: LLM | None = None

    def compile(self, llm: LLM | None = None) -> System:
        """Build the engine System; `llm` is the fallback backend for prompt rules that bound
        neither their own nor the board default."""
        return System([_rule_node(r, self.llm or llm) for r in self.rules])

    @property
    def system(self) -> System:
        return self.compile()

    def _prepare(
        self, seed: dict[str, Any], goal: str, budget: int | None, llm: LLM | None
    ) -> tuple[System, list[Fact], Terminate]:
        terminate: Terminate = Goal(lambda v: v.exists(goal))
        if budget is not None:
            terminate = terminate | Budget(budget)
        facts = [Fact(tag=tag, value=value) for tag, value in seed.items()]
        return self.compile(llm), facts, terminate

    async def run(
        self,
        seed: dict[str, Any],
        *,
        goal: str,
        budget: int | None = 100,
        policy: Policy | None = None,
        llm: LLM | None = None,
    ) -> Outcome:
        system, facts, terminate = self._prepare(seed, goal, budget, llm)
        run = await ReactiveExecutor().run(
            system, Store(), seed=facts, terminate=terminate, policy=policy
        )
        return Outcome(run, goal)

    async def stream(
        self,
        seed: dict[str, Any],
        *,
        goal: str,
        budget: int | None = 100,
        policy: Policy | None = None,
        llm: LLM | None = None,
    ) -> AsyncIterator[StepReport]:
        """The streaming form of .run: yields each StepReport as the run unfolds."""
        system, facts, terminate = self._prepare(seed, goal, budget, llm)
        async for report in ReactiveExecutor().stream(
            system, Store(), seed=facts, terminate=terminate, policy=policy
        ):
            yield report


def blackboard(*rules: Rule, llm: LLM | None = None) -> Board:
    """Assemble rules into a Board: nodes that self-activate when their condition holds, with
    no fixed topology. `llm` is the default backend for prompt rules that did not bind their
    own. Run it with board.run(seed, goal=...), drop to board.system for the raw engine, or
    wrap the board with nest to make it one typed node of a flow.
    """
    for r in rules:
        _check(r)
    names = [r.name for r in rules]
    dupes = sorted({n for n in names if names.count(n) > 1})
    if dupes:
        raise ValueError(f"duplicate rule names: {dupes}")
    return Board(tuple(rules), llm)
