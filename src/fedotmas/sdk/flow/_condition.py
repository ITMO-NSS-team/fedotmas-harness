"""Internal: the declarative predicate forms of the arrow surface.

Condition is data, not code: a program that emits systems can express a stop or routing
condition without writing a callable. _as_predicate folds the three accepted spellings
(callable, Condition, state key) into one callable.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Literal

from pydantic import BaseModel, model_validator


def _pick(state: Any, key: str) -> Any:
    if isinstance(state, dict):
        return state.get(key)
    return getattr(state, key, None)


class Condition(BaseModel):
    """A declarative predicate over one key of the state: data, not code, so a program that
    emits systems can express a stop or routing condition without writing a callable. `key`
    is looked up in the state (dict key or attribute, absent reads as None), `op` compares it
    to `value`. The default op is truthy, so Condition(key="approved") means state["approved"].
    """

    key: str
    op: Literal["truthy", "not", "eq", "ne", "gt", "lt", "gte", "lte", "exists"] = (
        "truthy"
    )
    value: Any = None

    @model_validator(mode="after")
    def _value_matches_op(self) -> Condition:
        if self.op in ("gt", "lt", "gte", "lte") and self.value is None:
            raise ValueError(
                f"Condition(key={self.key!r}, op={self.op!r}): an ordered comparison "
                "needs value="
            )
        if self.op in ("truthy", "not", "exists") and self.value is not None:
            raise ValueError(
                f"Condition(key={self.key!r}, op={self.op!r}): {self.op} does not "
                "compare, drop value="
            )
        return self

    def check(self, state: Any) -> bool:
        if self.op == "exists":
            return (
                self.key in state
                if isinstance(state, dict)
                else hasattr(state, self.key)
            )
        v = _pick(state, self.key)
        if self.op == "truthy":
            return bool(v)
        if self.op == "not":
            return not v
        if self.op == "eq":
            return v == self.value
        if self.op == "ne":
            return v != self.value
        if v is None:
            raise ValueError(
                f"Condition(key={self.key!r}, op={self.op!r}): the state has no "
                f"{self.key!r} to compare"
            )
        if self.op == "gt":
            return v > self.value
        if self.op == "lt":
            return v < self.value
        if self.op == "gte":
            return v >= self.value
        return v <= self.value


def _as_predicate(
    until: Callable[[Any], bool] | Condition | str,
) -> Callable[[Any], bool]:
    if isinstance(until, str):
        until = Condition(key=until)
    if isinstance(until, Condition):
        return until.check
    return until
