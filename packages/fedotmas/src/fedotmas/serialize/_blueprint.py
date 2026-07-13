from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from fedotmas._addressing import base_of
from fedotmas.engine.system import System
from fedotmas.serialize._graph import _edges


class BlueprintNode(BaseModel):
    name: str
    base: str
    kind: str
    reads: list[str]
    writes: list[str]
    params: dict[str, Any] = Field(default_factory=dict)
    meta: dict[str, Any] = Field(default_factory=dict)
    inner: Blueprint | None = None


class BlueprintEdge(BaseModel):
    src: str
    dst: str
    via: str


class Blueprint(BaseModel):
    """A compiled System projected to its declarative shape before any run: each node's kind,
    reads, declared writes, params and meta, plus the declared dataflow edges and the
    system's own discipline (`halt_on_error`; `policy` is the strategy's class name, a marker
    for a hole the blueprint cannot rebuild). Recurses into nested systems (nest, loop) and
    reads only the engine floor, so it is the same shape for a flow, a board, or their
    combination."""

    nodes: list[BlueprintNode]
    edges: list[BlueprintEdge] = Field(default_factory=list)
    policy: str | None = None
    halt_on_error: bool = True


def to_blueprint(system: System) -> Blueprint:
    """Project a compiled System to its Blueprint by collecting each node's self-description
    (Card). Static and read-only: it declares what each node is built to write, which the
    engine still confirms only by running (compare to_graph). A node exposing a live sub-system
    on its Card (nest, loop) recurses into it."""
    cards = [n.describe() for n in system.nodes]
    nodes: list[BlueprintNode] = []
    for card in cards:
        inner = card.system if isinstance(card.system, System) else None
        nodes.append(
            BlueprintNode(
                name=card.name,
                base=base_of(card.name),
                kind=card.kind,
                reads=card.reads,
                writes=card.writes,
                params=dict(card.params),
                meta=card.meta,
                inner=to_blueprint(inner) if inner is not None else None,
            )
        )
    specs = [(c.name, c.reads, c.writes) for c in cards]
    edges = [BlueprintEdge(src=s, dst=d, via=v) for s, d, v in _edges(specs)]
    return Blueprint(
        nodes=nodes,
        edges=edges,
        policy=type(system.policy).__name__ if system.policy else None,
        halt_on_error=system.halt_on_error,
    )


BlueprintNode.model_rebuild()
