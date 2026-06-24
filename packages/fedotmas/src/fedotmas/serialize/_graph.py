from __future__ import annotations

from pydantic import BaseModel, Field

from fedotmas.engine.report import Run
from fedotmas.engine.system import System


def _kind(name: str) -> str:
    """Best-effort node kind read off the compiled name scheme. A diagnostic label only:
    authoritative kinds arrive once nodes self-describe."""
    for mark, kind in (
        (":route", "branch.route"),
        (":join:", "branch.join"),
        (":iter", "loop.iter"),
        (":done", "loop.done"),
    ):
        if mark in name:
            return kind
    if name.startswith("alias:"):
        return "alias"
    if "#" in name:
        head = name.split("#", 1)[0]
        return head if head in {"gather", "into", "merge", "nest"} else "action"
    return "rule"


def _matches(tag: str, pattern: str) -> bool:
    if pattern.endswith("*"):
        return tag.startswith(pattern[:-1])
    return tag == pattern


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
    """Project a finished run to its dataflow graph. Node reads come from the System, writes
    and firing counts from the run's step trace; an edge means a node's observed write matched
    another node's read pattern. Read-only and surface-agnostic; pass `outcome.run` for the run.
    """
    produced: dict[str, set[str]] = {}
    fired: dict[str, int] = {}
    for report in run.steps:
        for name in report.fired:
            fired[name] = fired.get(name, 0) + 1
        for fact in report.writes:
            produced.setdefault(fact.producer, set()).add(fact.tag)

    nodes = [
        GraphNode(
            name=n.name,
            kind=_kind(n.name),
            reads=n.reads.split(),
            writes=sorted(produced.get(n.name, set())),
            fired=fired.get(n.name, 0),
        )
        for n in system.nodes
    ]

    writers = [(src, tag) for src, tags in produced.items() for tag in tags]
    seen: set[tuple[str, str, str]] = set()
    edges: list[GraphEdge] = []
    for n in system.nodes:
        for pattern in n.reads.split():
            for src, tag in writers:
                key = (src, n.name, pattern)
                if src != n.name and key not in seen and _matches(tag, pattern):
                    seen.add(key)
                    edges.append(GraphEdge(src=src, dst=n.name, via=pattern))
    return Graph(nodes=nodes, edges=edges)
