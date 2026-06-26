from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from fedotmas._outcome import Outcome
from fedotmas.engine.contract import Fact
from fedotmas.engine.executor import ReactiveExecutor
from fedotmas.engine.policy import Policy
from fedotmas.engine.store import Store
from fedotmas.engine.system import System
from fedotmas.engine.terminate import Budget, Goal, Terminate


async def run(
    system: System,
    seed: Mapping[str, Any],
    *,
    goal: str = "out",
    budget: int | None = 100,
    policy: Policy | None = None,
    halt_on_error: bool = True,
) -> Outcome:
    """Run a compiled System and read its goal fact back as an Outcome, the bare-System
    counterpart to Flow.run and Board.run (e.g. a System from from_blueprint or nest). `seed`
    is a tag to value map written as the initial facts; `goal` is the tag read back; `budget`
    caps the supersteps (None lifts the cap)."""
    terminate: Terminate = Goal(goal)
    if budget is not None:
        terminate = terminate | Budget(budget)
    facts = [Fact(tag=tag, value=value) for tag, value in seed.items()]
    r = await ReactiveExecutor(halt_on_error=halt_on_error).run(
        system, Store(), seed=facts, terminate=terminate, policy=policy
    )
    return Outcome(r, goal)
