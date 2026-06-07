"""Ready-set conflict resolution: fire-all, by-priority, auction."""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from fedotmas.engine.contract import Agent, View


class Policy(Protocol):
    def select(self, ready: list[Agent], view: View) -> list[Agent]: ...


class FireAll:
    def select(self, ready: list[Agent], view: View) -> list[Agent]:
        return ready


class AuctionSelect:
    def __init__(self, key: Callable[[Agent, View], float]) -> None:
        self.key = key

    def select(self, ready: list[Agent], view: View) -> list[Agent]:
        if not ready:
            return []
        return [max(ready, key=lambda a: self.key(a, view))]
