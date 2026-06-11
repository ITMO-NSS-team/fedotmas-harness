"""Run reporting: StepReport per superstep, Run for the whole execution."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from fedotmas.engine.contract import Fact, Status, View


@dataclass
class StepReport:
    """One superstep. `step` is the store clock stamped on this superstep's writes; it is
    monotonic across runs over the same store, so it can start above zero and skip when a
    feeder commits ahead. `index` is this report's position in the run's trace, the per-run
    axis that Budget counts."""

    step: int
    index: int
    fired: list[str]
    writes: list[Fact]
    errors: list[Fact] = field(default_factory=list)


@dataclass
class Run:
    status: Status
    steps: list[StepReport]
    view: View
    reason: Literal["terminate", "quiescence", "error"] = "terminate"
