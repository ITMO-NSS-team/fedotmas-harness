from __future__ import annotations

from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass
from typing import Any

from fedotmas._outcome import Outcome
from fedotmas.blackboard._rule import Rule
from fedotmas.engine.contract import Fact
from fedotmas.engine.executor import ReactiveExecutor
from fedotmas.engine.policy import Policy
from fedotmas.engine.report import StepReport
from fedotmas.engine.store import Store
from fedotmas.engine.system import System
from fedotmas.engine.terminate import Budget, Goal, Terminate


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
