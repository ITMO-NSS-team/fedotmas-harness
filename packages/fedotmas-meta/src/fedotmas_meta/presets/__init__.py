from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from fedotmas import Flow

from fedotmas_meta.presets._spec import (
    AgentSpec,
    Bound,
    Fill,
    ResolvedFill,
    RoleSpec,
    SystemSpec,
    check_fill,
    group,
    solo,
)

__all__ = [
    "AgentSpec",
    "Bound",
    "Fill",
    "Preset",
    "ResolvedFill",
    "RoleSpec",
    "SystemSpec",
    "check_fill",
    "group",
    "solo",
]


@runtime_checkable
class Preset(Protocol):
    """A pattern family with named role slots. `hint` is the one-liner the selector ranks on,
    `roles` says which slots to fill, `reserved` the wiring names a many role must avoid, and
    `build` turns a resolved filling into a runnable Flow. The catalog is the caller's: the
    package ships this protocol and the assembly mechanism, not a fixed menu of systems."""

    @property
    def name(self) -> str: ...
    @property
    def hint(self) -> str: ...
    @property
    def roles(self) -> tuple[RoleSpec, ...]: ...
    @property
    def reserved(self) -> frozenset[str]: ...
    def build(self, fill: ResolvedFill) -> Flow[Any, Any]: ...
