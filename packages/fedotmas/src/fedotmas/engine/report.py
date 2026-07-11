from __future__ import annotations

from dataclasses import dataclass, field

from fedotmas.engine.contract import Fact, Status, View


@dataclass
class StepReport:
    """One superstep. `step` is the store clock stamped on this superstep's writes; it is
    monotonic across runs over the same store, so it can start above zero and skip when a
    feeder commits ahead. `index` is this report's position in the run's trace, the per-run
    axis that Budget counts. `view` is the post-commit store this superstep produced; `scope`
    is the nesting path, `()` at the root and e.g. `("solve",)` inside a nest."""

    step: int
    index: int
    fired: list[str]
    writes: list[Fact]
    view: View
    errors: list[Fact] = field(default_factory=list)
    scope: tuple[str, ...] = ()


@dataclass
class Run:
    """A finished run: the trace, the final view, and `reason` — "error" or "quiescence"
    for the engine's own endings, else the label of the terminate condition that ended it
    ("goal", "budget", a custom class name lowercased)."""

    status: Status
    steps: list[StepReport]
    view: View
    reason: str = "quiescence"
    scope: tuple[str, ...] = ()
