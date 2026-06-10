"""Superstep loop, Run and StepReport."""

from __future__ import annotations

from dataclasses import dataclass, field

from fedotmas.engine.contract import Fact, Status, View


@dataclass
class StepReport:
    step: int
    fired: list[str]
    writes: list[Fact]
    errors: list[Fact] = field(default_factory=list)


@dataclass
class Run:
    status: Status
    steps: list[StepReport]
    view: View
    reason: str = "terminate"  # "terminate" | "quiescence" | "error"
