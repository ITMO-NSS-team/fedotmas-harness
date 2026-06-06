"""Superstep loop, Run and StepReport."""

from __future__ import annotations

from dataclasses import dataclass

from fedotmas.engine.contract import Fact, Status, View


@dataclass
class StepReport:
    step: int
    fired: list[str]
    writes: list[Fact]


@dataclass
class Run:
    status: Status
    steps: list[StepReport]
    view: View
