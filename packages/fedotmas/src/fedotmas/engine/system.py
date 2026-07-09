from __future__ import annotations

from collections.abc import AsyncIterator, Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from fedotmas.engine.contract import Fact, Node
from fedotmas.engine.outcome import Outcome
from fedotmas.engine.terminate import Budget, Goal, Terminate

if TYPE_CHECKING:
    from fedotmas.engine.plugin import Plugin, PluginDispatcher
    from fedotmas.engine.policy import Policy
    from fedotmas.engine.report import StepReport


@dataclass
class System:
    """The compiled unit the engine runs: a flat list of nodes over one store. `run` executes
    it to a goal fact and reads that fact back as an Outcome; `stream` is the same run
    yielded step by step. Flow.run and Board.run compile and delegate here, and a System from
    from_blueprint or nest runs the same way. Plugins passed at run time observe and
    intercept this system's own supersteps; reaching inside nested sub-systems requires
    baking them at compile (Flow.system and the run surfaces do this)."""

    nodes: list[Node]

    def __post_init__(self) -> None:
        names = [n.name for n in self.nodes]
        dupes = sorted({n for n in names if names.count(n) > 1})
        if dupes:
            raise ValueError(f"duplicate node names: {dupes}")

    def _setup(
        self,
        seed: Mapping[str, Any],
        goal: str,
        budget: int | None,
        halt_on_error: bool,
        plugins: Sequence[Plugin] | PluginDispatcher,
    ) -> tuple[Any, list[Fact], Terminate, PluginDispatcher]:
        # Imported here: executor imports System at module level.
        from fedotmas.engine.executor import ReactiveExecutor
        from fedotmas.engine.plugin import PluginDispatcher

        terminate: Terminate = Goal(goal)
        if budget is not None:
            terminate = terminate | Budget(budget)
        facts = [Fact(tag=tag, value=value) for tag, value in seed.items()]
        executor = ReactiveExecutor(halt_on_error=halt_on_error)
        return executor, facts, terminate, PluginDispatcher.of(plugins)

    async def run(
        self,
        seed: Mapping[str, Any],
        *,
        goal: str = "out",
        budget: int | None = 100,
        policy: Policy | None = None,
        halt_on_error: bool = True,
        plugins: Sequence[Plugin] | PluginDispatcher = (),
    ) -> Outcome:
        """Execute on a fresh store and read the goal fact back as an Outcome. `seed` is a
        tag -> value map written as the initial facts; `goal` is the tag read back; `budget`
        caps the supersteps (the default 100 is a runaway guard, None lifts it).
        `halt_on_error=False` keeps the run going past a failed node; the error still lands
        in `.errors` and `.ok` stays False."""
        from fedotmas.engine.store import Store

        executor, facts, terminate, dispatcher = self._setup(
            seed, goal, budget, halt_on_error, plugins
        )
        run = await executor.run(
            self,
            Store(),
            seed=facts,
            terminate=terminate,
            policy=policy,
            plugins=dispatcher,
        )
        return Outcome(run, goal)

    async def stream(
        self,
        seed: Mapping[str, Any],
        *,
        goal: str = "out",
        budget: int | None = 100,
        policy: Policy | None = None,
        halt_on_error: bool = True,
        plugins: Sequence[Plugin] | PluginDispatcher = (),
    ) -> AsyncIterator[StepReport]:
        """The streaming form of .run: yields each StepReport as the run unfolds."""
        from fedotmas.engine.store import Store

        executor, facts, terminate, dispatcher = self._setup(
            seed, goal, budget, halt_on_error, plugins
        )
        async for report in executor.stream(
            self,
            Store(),
            seed=facts,
            terminate=terminate,
            policy=policy,
            plugins=dispatcher,
        ):
            yield report
