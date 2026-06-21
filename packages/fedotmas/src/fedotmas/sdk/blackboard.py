from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable, Mapping, Sequence
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
from fedotmas.sdk._inject import bind_async
from fedotmas.sdk.flow._outcome import Outcome

# A rule's code body of either arity: `async (input)` or `async (input, view)`. The union keeps
# both forms typed; _inject.bind_async adapts the one-arg form to the (input, view) contract.
StepFn = Callable[[Any], Awaitable[Any]] | Callable[[Any, View], Awaitable[Any]]
_BoundFn = Callable[
    [Any, View], Awaitable[Any]
]  # the adapted body, always (input, view)
When = Callable[[View], bool]


def _produce_once(reads: str, writes: str) -> When:
    if reads:
        return lambda v: v.exists(reads) and not v.exists(writes)
    return lambda v: not v.exists(writes)


@dataclass
class Rule:
    """One self-activating blackboard node with a code body. When its condition holds, run the
    step and write the result to the `writes` fact; `reads` names the fact fed to the step as
    input (empty means none). The step is `fn`: code as `async (input)` or
    `async (input, view)`, where the trailing view is optional. `when` defaults to produce-once,
    fire when `reads` exists and `writes` does not yet, so a pipeline rule needs no trigger;
    supply `when` for opportunistic activation, as a sequence of tags that must all exist
    (`"!tag"` for must-not-exist) or, past presence tests, a callable over the View. `meta`
    rides along to the node, e.g. an auction bid that a Policy reads back off
    `node.describe().meta`. A rule whose body is a prompt instead of code is PromptRule in the
    fedotmas-llm extension, a subclass that overrides `_body`; the blackboard itself is
    model-free.
    """

    name: str
    fn: StepFn | None = None
    writes: str = ""
    reads: str = ""
    when: When | Sequence[str] | None = None
    meta: dict[str, Any] = field(default_factory=dict)

    def _body(self, bind: Mapping[str, Any]) -> _BoundFn:
        """The rule's step as an `(input, view)` body. The base rule adapts `fn`; an extension
        subclass overrides this to build its body from the run-scoped `bind` (e.g. a prompt
        rule resolving `bind["llm"]`). The one seam a new rule-kind implements."""
        if self.fn is None:
            raise ValueError(f"rule {self.name!r}: fn= is required")
        return bind_async(self.fn)

    def _validate(self) -> None:
        """Check the rule is well-formed before it is built. A subclass checks its own body
        requirement, then calls `_check_common` for the shared trigger/writes checks."""
        if self.fn is None:
            raise ValueError(f"rule {self.name!r}: fn= is required")
        self._check_common()

    def _check_common(self) -> None:
        if not self.writes:
            raise ValueError(f"rule {self.name!r}: writes= is required")
        if len(self.reads.split()) > 1:
            raise ValueError(
                f"rule {self.name!r}: reads= names one fact tag; condition on several "
                "facts with when= and read them off the view"
            )
        when = self.when
        if when is None or callable(when):
            return
        if isinstance(when, str) or not when or any(t in ("", "!") for t in when):
            raise ValueError(
                f"rule {self.name!r}: when= takes a sequence of non-empty tags"
            )
        clash = {t for t in when if not t.startswith("!")} & {
            t[1:] for t in when if t.startswith("!")
        }
        if clash:
            raise ValueError(
                f"rule {self.name!r}: when= both requires and forbids {sorted(clash)}"
            )

    def _as_when(self) -> tuple[When, list[str]]:
        """The rule's trigger plus the positive when tags, which join its re-fire identity."""
        when = self.when
        if when is None:
            return _produce_once(self.reads, self.writes), []
        if callable(when):
            return cast(When, when), []
        need = [t for t in when if not t.startswith("!")]
        veto = [t[1:] for t in when if t.startswith("!")]
        trigger = lambda v: (  # noqa: E731
            all(v.exists(t) for t in need) and not any(v.exists(t) for t in veto)
        )
        return trigger, need

    def _identity(self, need: list[str]) -> str:
        """The reads the engine dedups re-fires on: the input fact plus the positive when tags."""
        tags = [self.reads] if self.reads else []
        tags += [t for t in need if t not in tags]
        return " ".join(tags)

    def to_node(self, bind: Mapping[str, Any]) -> Node:
        """Compile the rule to an engine Node, resolving its body against the run-scoped `bind`.
        The blackboard machinery (trigger, re-fire identity, reads/writes, meta) lives here;
        only the body comes from `_body`, so an extension rule-kind reuses all of it."""
        fn = self._body(bind)

        async def invoke(input: Any, view: View) -> Result:
            value = await fn(view.value(self.reads) if self.reads else None, view)
            return Result(writes=[Fact(tag=self.writes, value=value)])

        trigger, need = self._as_when()
        return as_node(
            invoke,
            name=self.name,
            reads=self._identity(need),
            trigger=trigger,
            meta=self.meta,
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

    def compile(self, bind: Mapping[str, Any] | None = None) -> System:
        """Build the engine System; `bind` is the run-scoped binding map threaded to every
        rule's body (e.g. a default backend under "llm" for prompt rules). A rule that needs a
        binding nobody supplied fails here, not mid-run."""
        b = bind or {}
        return System([r.to_node(b) for r in self.rules])

    @property
    def system(self) -> System:
        return self.compile()

    def _prepare(
        self,
        seed: dict[str, Any],
        goal: str,
        budget: int | None,
        bind: Mapping[str, Any] | None,
    ) -> tuple[System, list[Fact], Terminate]:
        terminate: Terminate = Goal(lambda v: v.exists(goal))
        if budget is not None:
            terminate = terminate | Budget(budget)
        facts = [Fact(tag=tag, value=value) for tag, value in seed.items()]
        return self.compile(bind), facts, terminate

    async def run(
        self,
        seed: dict[str, Any],
        *,
        goal: str,
        bind: Mapping[str, Any] | None = None,
        budget: int | None = 100,
        policy: Policy | None = None,
        halt_on_error: bool = True,
    ) -> Outcome:
        system, facts, terminate = self._prepare(seed, goal, budget, bind)
        run = await ReactiveExecutor(halt_on_error=halt_on_error).run(
            system, Store(), seed=facts, terminate=terminate, policy=policy
        )
        return Outcome(run, goal)

    async def stream(
        self,
        seed: dict[str, Any],
        *,
        goal: str,
        bind: Mapping[str, Any] | None = None,
        budget: int | None = 100,
        policy: Policy | None = None,
        halt_on_error: bool = True,
    ) -> AsyncIterator[StepReport]:
        """The streaming form of .run: yields each StepReport as the run unfolds."""
        system, facts, terminate = self._prepare(seed, goal, budget, bind)
        async for report in ReactiveExecutor(halt_on_error=halt_on_error).stream(
            system, Store(), seed=facts, terminate=terminate, policy=policy
        ):
            yield report


def blackboard(*rules: Rule) -> Board:
    """Assemble rules into a Board: nodes that self-activate when their condition holds, with
    no fixed topology. Run it with board.run(seed, goal=...), drop to board.system for the raw
    engine, or wrap the board with nest to make it one typed node of a flow. A run-scoped
    bind={"llm": ...} reaches prompt rules (PromptRule, from fedotmas-llm); a board of code
    rules needs none.

    Example:
        score = Rule(name="score", reads="draft", writes="score", fn=grade)
        gate = Rule(name="gate", reads="score", writes="verdict", fn=decide)
        board = blackboard(score, gate)
        out = await board.run({"draft": "tea"}, goal="verdict")
    """
    for r in rules:
        r._validate()
    names = [r.name for r in rules]
    dupes = sorted({n for n in names if names.count(n) > 1})
    if dupes:
        raise ValueError(f"duplicate rule names: {dupes}")
    return Board(tuple(rules))
