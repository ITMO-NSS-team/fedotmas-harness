from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from fedotmas.engine.contract import View
from fedotmas.engine.report import StepReport


class Terminate(Protocol):
    """A stop condition checked after each superstep. Run surfaces take a sequence of these
    with any-of semantics: the first one that holds ends the run, and its lowercased class
    name becomes Run.reason ("goal", "budget", ...). The executor consults `done` again to
    name that reason, so it must be a pure function of its arguments."""

    def done(self, view: View, report: StepReport) -> bool: ...


class Budget:
    """Stop after `max_steps` supersteps. Counts the report index, the per-run axis, so it caps
    one run regardless of where the store clock started."""

    def __init__(self, max_steps: int) -> None:
        if max_steps < 1:
            raise ValueError(f"Budget needs max_steps >= 1, got {max_steps}")
        self.max_steps = max_steps

    def done(self, view: View, report: StepReport) -> bool:
        return report.index + 1 >= self.max_steps


class Goal:
    """Stop once a predicate over the store holds; a tag string is shorthand for that fact
    existing, so Goal("out") means v.exists("out")."""

    def __init__(self, predicate: Callable[[View], bool] | str) -> None:
        if isinstance(predicate, str):
            tag = predicate
            predicate = lambda v: v.exists(tag)  # noqa: E731
        self.predicate = predicate

    def done(self, view: View, report: StepReport) -> bool:
        return self.predicate(view)
