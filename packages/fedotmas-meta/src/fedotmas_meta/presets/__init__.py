from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from fedotmas import Flow

from fedotmas_meta.presets._board import BLACKBOARD
from fedotmas_meta.presets._spec import Fill, RoleSpec

__all__ = ["Fill", "Preset", "RoleSpec", "catalog", "get"]


@runtime_checkable
class Preset(Protocol):
    """A pattern family with named role slots. `hint` is the one-liner the selector ranks on,
    `roles` says which prompts to fill, `build` turns a filling into a runnable Flow."""

    @property
    def name(self) -> str: ...
    @property
    def hint(self) -> str: ...
    @property
    def roles(self) -> tuple[RoleSpec, ...]: ...
    def build(self, roles: Fill) -> Flow[Any, Any]: ...


# The flow presets (single/chain/debate/eval_optimizer/orchestrator/router) are dsl-based and
# out during the dsl refactor (full set at commit 2bd05ed); only blackboard builds without dsl.
_CATALOG: tuple[Preset, ...] = (BLACKBOARD,)


def catalog() -> tuple[Preset, ...]:
    """The closed menu of families, in selector display order."""
    return _CATALOG


def get(name: str) -> Preset:
    for p in _CATALOG:
        if p.name == name:
            return p
    raise KeyError(f"unknown preset {name!r}; one of {[p.name for p in _CATALOG]}")
