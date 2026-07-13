from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from fedotmas.engine.contract import Fact, Status, View
from fedotmas.engine.report import Run, StepReport


class RunError(RuntimeError):
    """A run did not finish clean: raised by Outcome.unwrap() and by the nest/loop boundary
    when an inner run breaks its contract. Failure stays data — `errors` holds the run's error
    facts, `reason` how it ended — so an executor catching it records a structured error fact
    (the carried facts nest as meta["causes"]) instead of a flattened string."""

    def __init__(
        self, message: str, *, errors: Sequence[Fact] = (), reason: str = "error"
    ) -> None:
        super().__init__(message)
        self.errors = list(errors)
        self.reason = reason


@dataclass
class Outcome:
    """The outcome of a run surface (System.run, Flow.run, Board.run): the engine Run plus the out tag,
    read back as one object. `value` is the produced output (None if the run never reached
    it), `ok` is "finished clean and produced the output", and `reason` says how the run
    ended: "goal" (the goal condition held), "error" (a node failed, see `errors`),
    "budget" (step cap hit first), or "stalled" (the system went quiet without producing
    the output: a wiring gap). A lenient system (halt_on_error=False) can end reason "goal"
    with `errors` non-empty; `ok` stays False, it never overlooks an error.
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
        """Every error fact this run recorded. A nest/loop failure is one fact whose
        meta["causes"] nests the inner facts' dumps, recursively — the whole failure tree."""
        return [e for s in self.run.steps for e in s.errors]

    @property
    def ok(self) -> bool:
        return self.run.status is Status.OK and self.run.view.exists(self.out)

    @property
    def reason(self) -> str:
        return "stalled" if self.run.reason == "quiescence" else self.run.reason

    def unwrap(self) -> Any:
        """Return the produced value, or raise RunError if the run did not finish clean. The
        complement to reading `.value`/`.ok` by hand: use it when a failed run should be an
        exception (a script, a test) rather than a None to branch on. The error names the
        reason and the failed nodes and carries their error facts."""
        if self.ok:
            return self.value
        detail = (
            "; ".join(f"{e.producer}: {e.value}" for e in self.errors)
            or "no output produced"
        )
        raise RunError(
            f"run did not succeed (reason={self.reason!r}): {detail}",
            errors=self.errors,
            reason=self.reason,
        )

    def __repr__(self) -> str:
        value = repr(self.value)
        if len(value) > 120:
            value = value[:117] + "..."
        return f"Outcome(ok={self.ok}, reason={self.reason!r}, value={value})"
