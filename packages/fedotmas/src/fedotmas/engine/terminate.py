from __future__ import annotations

from collections.abc import Callable
from functools import reduce
from typing import Protocol

from fedotmas.engine.contract import View
from fedotmas.engine.report import StepReport


class Terminate(Protocol):
    def done(self, view: View, report: StepReport) -> bool: ...


class _Term:
    def __and__(self, other: Terminate) -> Terminate:
        return _And(self, other)

    def __or__(self, other: Terminate) -> Terminate:
        return _Or(self, other)

    def done(self, view: View, report: StepReport) -> bool:
        raise NotImplementedError


class Budget(_Term):
    def __init__(self, max_steps: int) -> None:
        if max_steps < 1:
            raise ValueError(f"Budget needs max_steps >= 1, got {max_steps}")
        self.max_steps = max_steps

    def done(self, view: View, report: StepReport) -> bool:
        return report.index + 1 >= self.max_steps


class Goal(_Term):
    def __init__(self, predicate: Callable[[View], bool]) -> None:
        self.predicate = predicate

    def done(self, view: View, report: StepReport) -> bool:
        return self.predicate(view)


class Quiescence(_Term):
    def done(self, view: View, report: StepReport) -> bool:
        return not report.fired


class _And(_Term):
    def __init__(self, a: Terminate, b: Terminate) -> None:
        self.a, self.b = a, b

    def done(self, view: View, report: StepReport) -> bool:
        return self.a.done(view, report) and self.b.done(view, report)


class _Or(_Term):
    def __init__(self, a: Terminate, b: Terminate) -> None:
        self.a, self.b = a, b

    def done(self, view: View, report: StepReport) -> bool:
        return self.a.done(view, report) or self.b.done(view, report)


def all_of(*terms: Terminate) -> Terminate:
    if not terms:
        raise ValueError("all_of needs at least one Terminate")
    return reduce(_And, terms)


def any_of(*terms: Terminate) -> Terminate:
    if not terms:
        raise ValueError("any_of needs at least one Terminate")
    return reduce(_Or, terms)
