from __future__ import annotations

from collections.abc import Callable
from functools import reduce
from typing import Protocol

from fedotmas.engine.contract import View
from fedotmas.engine.report import StepReport


class Terminate(Protocol):
    """A stop condition checked after each superstep. Combine the built-ins with `&` and `|`,
    or fold many with all_of/any_of."""

    def done(self, view: View, report: StepReport) -> bool: ...


class _Term:
    def __and__(self, other: Terminate) -> Terminate:
        return _And(self, other)

    def __or__(self, other: Terminate) -> Terminate:
        return _Or(self, other)

    def done(self, view: View, report: StepReport) -> bool:
        raise NotImplementedError


class Budget(_Term):
    """Stop after `max_steps` supersteps. Counts the report index, the per-run axis, so it caps
    one run regardless of where the store clock started."""

    def __init__(self, max_steps: int) -> None:
        if max_steps < 1:
            raise ValueError(f"Budget needs max_steps >= 1, got {max_steps}")
        self.max_steps = max_steps

    def done(self, view: View, report: StepReport) -> bool:
        return report.index + 1 >= self.max_steps


class Goal(_Term):
    """Stop once a predicate over the store holds, e.g. the output fact exists."""

    def __init__(self, predicate: Callable[[View], bool]) -> None:
        self.predicate = predicate

    def done(self, view: View, report: StepReport) -> bool:
        return self.predicate(view)


class Quiescence(_Term):
    """Stop when a superstep fires nothing: the system has gone quiet on its own."""

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
    """Stop when every term holds. The n-ary form of `&`."""
    if not terms:
        raise ValueError("all_of needs at least one Terminate")
    return reduce(_And, terms)


def any_of(*terms: Terminate) -> Terminate:
    """Stop when any term holds. The n-ary form of `|`."""
    if not terms:
        raise ValueError("any_of needs at least one Terminate")
    return reduce(_Or, terms)
