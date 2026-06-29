from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any, Literal, Union, cast

from pydantic import BaseModel, ConfigDict, Field, model_validator

from fedotmas._inject import bind_pred
from fedotmas.engine.contract import View

Op = Literal["truthy", "not", "eq", "ne", "gt", "lt", "gte", "lte", "exists"]


def _pick(state: Any, key: str) -> Any:
    if isinstance(state, dict):
        return state.get(key)
    return getattr(state, key, None)


class Source:
    """How a predicate reads one named slot. The slot fixes the domain, a loop's state value
    or the blackboard view, so the same Condition serves both: until reads the state, when and
    Goal read the view."""

    def get(self, key: str) -> Any:
        raise NotImplementedError

    def has(self, key: str) -> bool:
        raise NotImplementedError


class _State(Source):
    def __init__(self, state: Any) -> None:
        self._state = state

    def get(self, key: str) -> Any:
        return _pick(self._state, key)

    def has(self, key: str) -> bool:
        s = self._state
        return key in s if isinstance(s, dict) else hasattr(s, key)


class _View(Source):
    def __init__(self, view: View) -> None:
        self._view = view

    def get(self, key: str) -> Any:
        return self._view.value(key)

    def has(self, key: str) -> bool:
        return self._view.exists(key)


def _source(src: Any) -> Source:
    return src if isinstance(src, Source) else _State(src)


class Predicate(BaseModel):
    """Boolean algebra over a Source, the base of the leaf Condition and its and/or/not
    compositions. `&`/`|`/`~` mirror Terminate; calling the predicate as `(view) -> bool` reads
    the view, so it drops straight into Goal and a board's when= with no adapter."""

    def check(self, src: Any) -> bool:
        raise NotImplementedError

    def positive_keys(self) -> list[str]:
        """The keys that must be present for the predicate to hold, the re-fire reads a board
        rule dedups on. Negated branches contribute none."""
        return []

    def __and__(self, other: Predicate) -> Predicate:
        return AllOf(operands=cast("list[_Node]", [self, other]))

    def __or__(self, other: Predicate) -> Predicate:
        return AnyOf(operands=cast("list[_Node]", [self, other]))

    def __invert__(self) -> Predicate:
        return Not(operand=cast("_Node", self))

    def __call__(self, view: View) -> bool:
        return self.check(_View(view))


class Condition(Predicate):
    """A declarative predicate over one key: data, not code, so a program emitting systems can
    express a stop or trigger condition without writing a callable. `key` is looked up in the
    source (a loop's state or the blackboard view, dict key or attribute, absent reads as None),
    `op` compares it to `value`. The default op is truthy, so Condition(key="approved") means the
    value is truthy. Compose several with `&`/`|`/`~`."""

    key: str
    op: Op = "truthy"
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

    def check(self, src: Any) -> bool:
        s = _source(src)
        if self.op == "exists":
            return s.has(self.key)
        v = s.get(self.key)
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
                f"Condition(key={self.key!r}, op={self.op!r}): the source has no "
                f"{self.key!r} to compare"
            )
        if self.op == "gt":
            return v > self.value
        if self.op == "lt":
            return v < self.value
        if self.op == "gte":
            return v >= self.value
        return v <= self.value

    def positive_keys(self) -> list[str]:
        return [self.key]


class Not(Predicate):
    """Negation of a predicate. The `!tag` form of a when= tag list builds one over an exists
    check."""

    model_config = ConfigDict(populate_by_name=True)
    operand: _Node = Field(serialization_alias="not", validation_alias="not")

    def check(self, src: Any) -> bool:
        return not self.operand.check(_source(src))


class AllOf(Predicate):
    """Conjunction: every operand holds. The `&` form and what a when= tag list folds into."""

    model_config = ConfigDict(populate_by_name=True)
    operands: list[_Node] = Field(serialization_alias="all", validation_alias="all")

    def check(self, src: Any) -> bool:
        s = _source(src)
        return all(o.check(s) for o in self.operands)

    def positive_keys(self) -> list[str]:
        return [k for o in self.operands for k in o.positive_keys()]


class AnyOf(Predicate):
    """Disjunction: some operand holds. The `|` form."""

    model_config = ConfigDict(populate_by_name=True)
    operands: list[_Node] = Field(serialization_alias="any", validation_alias="any")

    def check(self, src: Any) -> bool:
        s = _source(src)
        return any(o.check(s) for o in self.operands)

    def positive_keys(self) -> list[str]:
        return [k for o in self.operands for k in o.positive_keys()]


_Node = Union[Condition, Not, AllOf, AnyOf]

Not.model_rebuild()
AllOf.model_rebuild()
AnyOf.model_rebuild()


def _tags(tags: Sequence[str]) -> Predicate:
    """Fold a when= tag list into a predicate: each tag is an exists check, `!tag` forbids it,
    joined by all-of. The compact, declarative spelling of the common board trigger."""
    leaves: list[_Node] = []
    for t in tags:
        if not isinstance(t, str) or t in ("", "!"):
            raise ValueError("a when= tag list takes non-empty tags, '!tag' to forbid")
        if t.startswith("!"):
            leaves.append(Not(operand=Condition(key=t[1:], op="exists")))
        else:
            leaves.append(Condition(key=t, op="exists"))
    return leaves[0] if len(leaves) == 1 else AllOf(operands=leaves)


def as_condition(spec: Predicate | str | Sequence[str]) -> Predicate:
    """Fold the declarative spellings into one Predicate: a Condition (or its `&`/`|`/`~`
    composition) passes through, a str is a truthy Condition over that key, a tag sequence is an
    all-of existence check. The compact list is a wire form too, not just an authoring sugar."""
    if isinstance(spec, Predicate):
        return spec
    if isinstance(spec, str):
        return Condition(key=spec)
    if isinstance(spec, Sequence):
        return _tags(spec)
    raise TypeError(f"not a condition spec: {spec!r}")


def spec_of(pred: Predicate | None) -> dict[str, Any] | str:
    """The serializable shape of a compiled predicate for a Card: the model dump for a
    declarative one (a dict, the from_blueprint signal that it round-trips), the string
    'callable' for an opaque escape the blueprint cannot carry."""
    if pred is None:
        return "callable"
    return pred.model_dump(mode="json", by_alias=True, exclude_defaults=True)


def _tree(spec: dict[str, Any]) -> Predicate:
    """Rebuild one predicate node from its by-alias dump, recursing into composites."""
    if "all" in spec:
        return AllOf(operands=cast("list[_Node]", [_tree(o) for o in spec["all"]]))
    if "any" in spec:
        return AnyOf(operands=cast("list[_Node]", [_tree(o) for o in spec["any"]]))
    if "not" in spec:
        return Not(operand=cast("_Node", _tree(spec["not"])))
    return Condition.model_validate(spec)


def from_spec(spec: dict[str, Any] | str) -> Predicate | None:
    """Inverse of spec_of: rebuild the predicate tree from the dict a declarative when/until
    dumped to, None for an opaque marker string ('callable', 'produce-once') the blueprint
    cannot carry back to code. The from_blueprint counterpart of spec_of."""
    return None if isinstance(spec, str) else _tree(spec)


def state_predicate(
    spec: Callable[[Any], bool] | Callable[[Any, View], bool] | Predicate | str,
) -> tuple[Callable[[Any, View], bool], Predicate | None]:
    """Compile a loop's until to a `(state, view) -> bool` plus its declarative form (None when
    the spec is an opaque callable, the one non-serializable escape). A callable may take the
    state alone or the state and the view."""
    if not isinstance(spec, (Predicate, str)):
        return bind_pred(spec), None
    pred = as_condition(spec)
    return (lambda state, view: pred.check(_State(state))), pred


def view_predicate(
    spec: Callable[[View], bool] | Predicate | str | Sequence[str],
) -> tuple[Callable[[View], bool], Predicate | None]:
    """Compile a view predicate (a board when) to a `(view) -> bool` plus its declarative form
    (None for an opaque callable)."""
    if not isinstance(spec, (Predicate, str, Sequence)):
        return spec, None
    pred = as_condition(cast("Predicate | str | Sequence[str]", spec))
    return (lambda view: pred.check(_View(view))), pred
