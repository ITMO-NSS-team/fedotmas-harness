from __future__ import annotations

from collections.abc import AsyncIterator, Mapping, Sequence
from dataclasses import KW_ONLY, dataclass
from typing import TYPE_CHECKING, Any

from fedotmas.blackboard._rule import Rule
from fedotmas.engine.plugin import PluginDispatcher
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
    compiles to (see System). `system()` is the Compilable face: the engine System for
    executor-level control, for nest() when the board becomes one node of a flow, and for
    Rule(nest=) when it becomes one rule of another board.
    """

    rules: tuple[Rule, ...]
    _: KW_ONLY
    policy: Policy | None = None
    halt_on_error: bool = True

    def system(
        self,
        *,
        entry: str | None = None,
        out: str | None = None,
        bind: Mapping[str, Any] | None = None,
        plugins: Sequence[Plugin] | PluginDispatcher = (),
    ) -> System:
        """Build the engine System. `bind` is the run-scoped binding map threaded to every
        rule's body (e.g. a default backend under "llm" for prompt rules); a rule that needs
        a binding nobody supplied fails here, not mid-run. `plugins` is the dispatcher whose
        nested faces reach nest-rule interiors. A board owns its tags, so unlike a flow the
        boundary tags are references, not assignments: `entry` is free (a rule may pick it up
        through any when=), while a given `out` must be some rule's writes — a goal nothing
        writes is a guaranteed stall, caught here instead."""
        if out is not None and out not in {r.writes for r in self.rules}:
            raise ValueError(f"board: no rule writes {out!r}")
        b = bind or {}
        dispatcher = PluginDispatcher.of(plugins)
        return System(
            [r.to_node(b, dispatcher) for r in self.rules],
            policy=self.policy,
            halt_on_error=self.halt_on_error,
        )

    async def run(
        self,
        seed: dict[str, Any],
        *,
        goal: str,
        bind: Mapping[str, Any] | None = None,
        budget: int | None = 100,
        plugins: Sequence[Plugin] = (),
    ) -> Outcome:
        dispatcher = PluginDispatcher.of(plugins)
        return await self.system(bind=bind, plugins=dispatcher).run(
            seed, goal=goal, budget=budget, plugins=dispatcher
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
        dispatcher = PluginDispatcher.of(plugins)
        async for report in self.system(bind=bind, plugins=dispatcher).stream(
            seed, goal=goal, budget=budget, plugins=dispatcher
        ):
            yield report


def blackboard(
    *rules: Rule,
    policy: Policy | None = None,
    halt_on_error: bool = True,
) -> Board:
    """Assemble rules into a Board: nodes that self-activate when their condition holds, with
    no fixed topology. Run it with board.run(seed, goal=...), drop to board.system() for the
    raw engine, or wrap the board with nest to make it one typed node of a flow. A rule may
    itself be a whole sub-system (Rule(nest=inner_board, ...)), which is how boards nest in
    boards. A run-scoped bind={"llm": ...} reaches prompt rules (PromptRule, from
    fedotmas-llm); a board of code rules needs none. `policy` arbitrates which armed rules
    fire each superstep (e.g. AuctionSelect for a contract-net board); `halt_on_error=False`
    declares a lenient board whose failed rules are recorded, not fatal. Both travel with the
    board through nest and the blueprint round-trip. A failed rule's record is an
    `error:{name}` fact in the store, so on a lenient board another rule can react to it —
    e.g. a repair rule with when=["error:planner"] fires when the planner fails.

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
