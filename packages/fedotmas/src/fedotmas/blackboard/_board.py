from __future__ import annotations

from collections.abc import AsyncIterator, Mapping, Sequence
from dataclasses import KW_ONLY, dataclass
from typing import TYPE_CHECKING, Any

from fedotmas.blackboard._rule import Rule
from fedotmas.engine.system import System

if TYPE_CHECKING:
    from fedotmas.engine.outcome import Outcome
    from fedotmas.engine.plugin import Plugin
    from fedotmas.engine.policy import Policy
    from fedotmas.engine.report import StepReport


@dataclass
class Board:
    """An assembled blackboard: the rules plus a run surface symmetric with Flow.run. A board
    has no single typed output, so `run` takes the seed facts as a tag -> value dict and a
    `goal` tag to read the result back from; both delegate to System.run/System.stream.
    `policy` and `halt_on_error` are the board's own discipline, stamped onto every System it
    compiles to (see System). `compile` produces the engine System (`system` is its
    no-argument form), for executor-level control and for what nest() picks up when a board
    becomes one node of a flow.
    """

    rules: tuple[Rule, ...]
    _: KW_ONLY
    policy: Policy | None = None
    halt_on_error: bool = True

    def compile(self, bind: Mapping[str, Any] | None = None) -> System:
        """Build the engine System; `bind` is the run-scoped binding map threaded to every
        rule's body (e.g. a default backend under "llm" for prompt rules). A rule that needs a
        binding nobody supplied fails here, not mid-run."""
        b = bind or {}
        return System(
            [r.to_node(b) for r in self.rules],
            policy=self.policy,
            halt_on_error=self.halt_on_error,
        )

    @property
    def system(self) -> System:
        return self.compile()

    async def run(
        self,
        seed: dict[str, Any],
        *,
        goal: str,
        bind: Mapping[str, Any] | None = None,
        budget: int | None = 100,
        plugins: Sequence[Plugin] = (),
    ) -> Outcome:
        return await self.compile(bind).run(
            seed, goal=goal, budget=budget, plugins=plugins
        )

    async def stream(
        self,
        seed: dict[str, Any],
        *,
        goal: str,
        bind: Mapping[str, Any] | None = None,
        budget: int | None = 100,
        plugins: Sequence[Plugin] = (),
    ) -> AsyncIterator[StepReport]:
        """The streaming form of .run: yields each StepReport as the run unfolds."""
        async for report in self.compile(bind).stream(
            seed, goal=goal, budget=budget, plugins=plugins
        ):
            yield report


def blackboard(
    *rules: Rule,
    policy: Policy | None = None,
    halt_on_error: bool = True,
) -> Board:
    """Assemble rules into a Board: nodes that self-activate when their condition holds, with
    no fixed topology. Run it with board.run(seed, goal=...), drop to board.system for the raw
    engine, or wrap the board with nest to make it one typed node of a flow. A run-scoped
    bind={"llm": ...} reaches prompt rules (PromptRule, from fedotmas-llm); a board of code
    rules needs none. `policy` arbitrates which armed rules fire each superstep (e.g.
    AuctionSelect for a contract-net board); `halt_on_error=False` declares a lenient board
    whose failed rules are recorded, not fatal. Both travel with the board through nest and
    the blueprint round-trip.

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
    return Board(tuple(rules), policy=policy, halt_on_error=halt_on_error)
