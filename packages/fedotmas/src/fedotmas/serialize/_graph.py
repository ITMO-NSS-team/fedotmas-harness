from __future__ import annotations

from pydantic import BaseModel, Field

from fedotmas.engine.report import Run
from fedotmas.engine.system import System
from fedotmas.serialize._dataflow import _edges


class GraphNode(BaseModel):
    name: str
    kind: str
    reads: list[str]
    writes: list[str]
    fired: int


class GraphEdge(BaseModel):
    src: str
    dst: str
    via: str


class Graph(BaseModel):
    """A run projected to a tag-level dataflow graph: every node of the System plus the edges
    where a producer's write feeds a consumer's read. Reads only the engine floor (System +
    Run), so it is the same shape for a flow, a board, or any future surface."""

    nodes: list[GraphNode]
    edges: list[GraphEdge] = Field(default_factory=list)


def to_graph(system: System, run: Run) -> Graph:
    """Project a finished run to its dataflow graph. Node kind/reads come from each node's
    self-description, writes and firing counts from the run's step trace; an edge means a
    node's observed write matched another node's read pattern. Read-only and surface-agnostic;
    pass `outcome.run` for the run."""
    produced: dict[str, set[str]] = {}
    fired: dict[str, int] = {}
    for report in run.steps:
        for name in report.fired:
            fired[name] = fired.get(name, 0) + 1
        for fact in report.writes:
            produced.setdefault(fact.producer, set()).add(fact.tag)

    nodes: list[GraphNode] = []
    specs: list[tuple[str, list[str], list[str]]] = []
    for n in system.nodes:
        reads = n.reads.split()
        writes = sorted(produced.get(n.name, set()))
        nodes.append(
            GraphNode(
                name=n.name,
                kind=n.describe().kind,
                reads=reads,
                writes=writes,
                fired=fired.get(n.name, 0),
            )
        )
        specs.append((n.name, reads, writes))
    edges = [GraphEdge(src=s, dst=d, via=v) for s, d, v in _edges(specs)]
    return Graph(nodes=nodes, edges=edges)
