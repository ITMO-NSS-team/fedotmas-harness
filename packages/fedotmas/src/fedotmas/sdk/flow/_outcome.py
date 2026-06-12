"""Internal: Outcome, the one object a run surface returns (Flow.run, Board.run)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from fedotmas.engine.contract import Fact, Status, View
from fedotmas.engine.report import Run, StepReport


@dataclass
class Outcome:
    """The outcome of a run surface (Flow.run, Board.run): the engine Run plus the out tag,
    read back as one object. `value` is the produced output (None if the run never reached
    it), `ok` is "finished clean and produced the output", and `reason` says how the run
    ended: "goal" (output produced), "error" (a node failed, see `errors`), "budget" (step
    cap hit first), or "stalled" (the system went quiet without producing the output: a
    wiring gap). Under halt_on_error=False a run can end reason "goal" with `errors`
    non-empty; `ok` stays False, it never overlooks an error.
    """

    run: Run
    out: str

    @property
    def view(self) -> View:
        return self.run.view

    @property
    def steps(self) -> list[StepReport]:
        return self.run.steps

    @property
    def value(self) -> Any:
        return self.run.view.value(self.out)

    @property
    def errors(self) -> list[Fact]:
        return [e for s in self.run.steps for e in s.errors]

    @property
    def ok(self) -> bool:
        return self.run.status is Status.OK and self.run.view.exists(self.out)

    @property
    def reason(self) -> Literal["goal", "error", "budget", "stalled"]:
        if self.run.reason == "error":
            return "error"
        if self.run.view.exists(self.out):
            return "goal"
        return "stalled" if self.run.reason == "quiescence" else "budget"

    def __repr__(self) -> str:
        value = repr(self.value)
        if len(value) > 120:
            value = value[:117] + "..."
        return f"Outcome(ok={self.ok}, reason={self.reason!r}, value={value})"
