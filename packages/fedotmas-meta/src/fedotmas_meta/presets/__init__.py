"""Pattern presets: prewired MAS families that a meta-agent (or a person) fills with
roles. Every preset builds a Flow; data-backed presets also expose the manifest document
behind it, so the artifact stays patchable data."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from fedotmas import dsl
from fedotmas.sdk import Flow

from fedotmas_meta.presets._board import BLACKBOARD
from fedotmas_meta.presets._flow import (
    CHAIN,
    DEBATE,
    EVAL_OPTIMIZER,
    ORCHESTRATOR,
    ROUTER,
    SINGLE,
)
from fedotmas_meta.presets._spec import Fill, RoleSpec

__all__ = ["DataPreset", "Fill", "Preset", "RoleSpec", "catalog", "get"]


@runtime_checkable
class Preset(Protocol):
    @property
    def name(self) -> str: ...
    @property
    def hint(self) -> str: ...
    @property
    def roles(self) -> tuple[RoleSpec, ...]: ...
    def build(self, roles: Fill) -> Flow[Any, Any]: ...


@runtime_checkable
class DataPreset(Preset, Protocol):
    def manifest(self, roles: Fill) -> dsl.Manifest: ...


_CATALOG: tuple[Preset, ...] = (
    SINGLE,
    CHAIN,
    DEBATE,
    EVAL_OPTIMIZER,
    ORCHESTRATOR,
    ROUTER,
    BLACKBOARD,
)


def catalog() -> tuple[Preset, ...]:
    """The closed menu of families, in selector display order."""
    return _CATALOG


def get(name: str) -> Preset:
    for p in _CATALOG:
        if p.name == name:
            return p
    raise KeyError(f"unknown preset {name!r}; one of {[p.name for p in _CATALOG]}")
