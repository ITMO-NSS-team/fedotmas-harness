from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from fedotmas.engine.system import System
from fedotmas.serialize._blueprint import Blueprint


class ReconstructError(Exception):
    """from_blueprint could not rebuild a node: a body the blueprint cannot carry is missing
    from Deps, or the node is a hole the lacquer marked non-declarative (a callable until or
    select, an unknown kind)."""


@dataclass
class Deps:
    """What from_blueprint injects back into a rebuilt System. `bodies` fills the opaque code
    the blueprint cannot carry, keyed by node base name with any `#n` suffix stripped (an
    action's function, a code rule's fn). `bind` is the run-scoped resource map (e.g. an "llm"
    backend) for nodes that resolve one. The two are different by design: a body is the node's
    definition, a bind value a swappable resource."""

    bodies: dict[str, Callable[..., Any]] = field(default_factory=dict)
    bind: dict[str, Any] = field(default_factory=dict)


def from_blueprint(blueprint: Blueprint, deps: Deps) -> System:
    """Rebuild a runnable System from its declarative floor, the inverse of to_blueprint. Each
    node is reconstructed from its kind and params, with opaque bodies drawn from `deps` by
    name; a declarative control spec (state-key until/select) is recompiled to its predicate.
    The round-trip is the contract: `to_blueprint(from_blueprint(bp, deps)) == bp` and the
    rebuilt system runs to the same output."""
    raise NotImplementedError("from_blueprint: pending the contract decision")
