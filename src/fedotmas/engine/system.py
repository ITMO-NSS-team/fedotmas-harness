"""System: the compiled set of agents and their interaction rules. Produced by the DSL, run by an executor."""

from __future__ import annotations

from dataclasses import dataclass

from fedotmas.engine.contract import Agent


@dataclass
class System:
    agents: list[Agent]
