"""System: the compiled set of nodes and their interaction rules. Produced by the SDK surfaces, run by an executor."""

from __future__ import annotations

from dataclasses import dataclass

from fedotmas.engine.contract import Node


@dataclass
class System:
    nodes: list[Node]
