"""Termination conditions: goal, quiescence, budget."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol

from fedotmas.engine.contract import View


class Terminate(Protocol):
    def done(self, view: View, report: Any) -> bool: ...


class _Term:
    def __and__(self, other: _Term) -> _Term:
        return _And(self, other)

    def __or__(self, other: _Term) -> _Term:
        return _Or(self, other)

    def done(self, view: View, report: Any) -> bool:
        raise NotImplementedError


class Budget(_Term):
    def __init__(self, max_steps: int) -> None:
        self.max_steps = max_steps

    def done(self, view: View, report: Any) -> bool:
        return report.step + 1 >= self.max_steps


class Goal(_Term):
    def __init__(self, predicate: Callable[[View], bool]) -> None:
        self.predicate = predicate

    def done(self, view: View, report: Any) -> bool:
        return self.predicate(view)


class Quiescence(_Term):
    def done(self, view: View, report: Any) -> bool:
        return not report.fired


class _And(_Term):
    def __init__(self, a: _Term, b: _Term) -> None:
        self.a, self.b = a, b

    def done(self, view: View, report: Any) -> bool:
        return self.a.done(view, report) and self.b.done(view, report)


class _Or(_Term):
    def __init__(self, a: _Term, b: _Term) -> None:
        self.a, self.b = a, b

    def done(self, view: View, report: Any) -> bool:
        return self.a.done(view, report) or self.b.done(view, report)
