from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

Fill = Mapping[str, "str | dict[str, str]"]


@dataclass(frozen=True)
class RoleSpec:
    """One slot of a preset: `many=False` takes a prompt, `many=True` a name -> prompt
    dict whose keys become node names and routing labels."""

    name: str
    hint: str
    many: bool = False


def check_fill(
    preset: str,
    roles: tuple[RoleSpec, ...],
    fill: Fill,
    reserved: frozenset[str] = frozenset(),
) -> dict[str, Any]:
    """Validate a role filling against a preset's slots: every role present and no extras, each
    value the right shape (prompt string, or non-empty name -> prompt dict for many=True), and
    no `many` keys clashing with `reserved` wiring names. Returns the filling as a plain dict."""
    expected = {r.name for r in roles}
    missing = sorted(expected - fill.keys())
    unknown = sorted(fill.keys() - expected)
    if missing or unknown:
        raise ValueError(
            f"preset {preset!r}: missing roles {missing}, unknown roles {unknown}"
        )
    for r in roles:
        value = fill[r.name]
        if r.many:
            if not isinstance(value, dict) or not value:
                raise ValueError(
                    f"preset {preset!r}: role {r.name!r} takes a non-empty"
                    " name -> prompt dict"
                )
            taken = sorted(value.keys() & reserved)
            if taken:
                raise ValueError(
                    f"preset {preset!r}: names {taken} are reserved by the wiring"
                )
        elif not isinstance(value, str) or not value:
            raise ValueError(
                f"preset {preset!r}: role {r.name!r} takes a prompt string"
            )
    return dict(fill)
