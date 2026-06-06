"""Ready-set conflict resolution: fire-all, by-priority, auction."""

from __future__ import annotations

from typing import Protocol

from fedotmas.engine.contract import Agent, View


class Policy(Protocol):
    def select(self, ready: list[Agent], view: View) -> list[Agent]: ...


class FireAll:
    def select(self, ready: list[Agent], view: View) -> list[Agent]:
        return ready
