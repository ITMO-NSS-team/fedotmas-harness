"""System: the compiled set of nodes. Produced by the SDK surfaces, run by an executor."""

from __future__ import annotations

from dataclasses import dataclass

from fedotmas.engine.contract import Node


@dataclass
class System:
    nodes: list[Node]

    def __post_init__(self) -> None:
        names = [n.name for n in self.nodes]
        dupes = sorted({n for n in names if names.count(n) > 1})
        if dupes:
            raise ValueError(f"duplicate node names: {dupes}")
