from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, cast

from fedotmas_llm import LLM, Tool
from pydantic import BaseModel, Field


class AgentSpec(BaseModel):
    """One agent as fillable strings: the prompt, an optional model key (resolved against the
    `models` registry at assembly, None falls back to the run-scoped `bind={"llm": ...}`), and
    tool names (a registry key for a local fn, a url for an MCP server). Pure data, so a spec
    round-trips through json and a meta-agent authors one without touching an SDK."""

    model_config = {"extra": "forbid"}

    prompt: str = Field(min_length=1)
    model: str | None = None
    tools: list[str] = Field(default_factory=list)


class SystemSpec(BaseModel):
    """A whole system as a preset name plus its filling: each role maps to an AgentSpec, or to
    a name -> AgentSpec dict for a `many` role. The serializable proposal a meta-agent emits."""

    model_config = {"extra": "forbid"}

    preset: str
    fill: dict[str, "AgentSpec | dict[str, AgentSpec]"]


@dataclass(frozen=True)
class Bound:
    """An AgentSpec with its strings resolved: the prompt, the bound backend (or None to defer
    to the run binding), and the tool descriptors. The form a preset wires into nodes."""

    prompt: str
    llm: LLM | None = None
    tools: tuple[Tool, ...] = ()


@dataclass(frozen=True)
class RoleSpec:
    """One slot of a preset: `many=False` takes one AgentSpec, `many=True` a name -> AgentSpec
    dict whose keys become node names and routing labels."""

    name: str
    hint: str
    many: bool = False


Fill = Mapping[str, "AgentSpec | dict[str, AgentSpec]"]
ResolvedFill = Mapping[str, "Bound | dict[str, Bound]"]


def solo(value: Bound | dict[str, Bound]) -> Bound:
    """Narrow a resolved single-role value to its Bound (the preset knows it is not many)."""
    if not isinstance(value, Bound):
        raise TypeError(f"expected a single Bound, got {type(value).__name__}")
    return value


def group(value: Bound | dict[str, Bound]) -> dict[str, Bound]:
    """Narrow a resolved many-role value to its name -> Bound dict."""
    if not isinstance(value, dict):
        raise TypeError(f"expected a name -> Bound dict, got {type(value).__name__}")
    return cast("dict[str, Bound]", value)


def check_fill(
    preset: str,
    roles: tuple[RoleSpec, ...],
    fill: Fill,
    reserved: frozenset[str] = frozenset(),
) -> dict[str, Any]:
    """Validate a filling against a preset's slots: every role present and no extras, each
    value the right shape (one AgentSpec, or a non-empty name -> AgentSpec dict for many=True),
    and no `many` keys clashing with `reserved` wiring names. Returns the filling as a dict."""
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
                    " name -> AgentSpec dict"
                )
            if not all(isinstance(v, AgentSpec) for v in value.values()):
                raise ValueError(
                    f"preset {preset!r}: role {r.name!r} entries must be AgentSpecs"
                )
            taken = sorted(value.keys() & reserved)
            if taken:
                raise ValueError(
                    f"preset {preset!r}: names {taken} are reserved by the wiring"
                )
        elif not isinstance(value, AgentSpec):
            raise ValueError(f"preset {preset!r}: role {r.name!r} takes an AgentSpec")
    return dict(fill)
