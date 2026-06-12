"""Ready-set conflict resolution: fire-all, by-priority, auction."""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from fedotmas.engine.contract import Node, View


class Policy(Protocol):
    def select(self, ready: list[Node], view: View) -> list[Node]: ...


class FireAll:
    def select(self, ready: list[Node], view: View) -> list[Node]:
        return ready


class AuctionSelect:
    def __init__(self, key: Callable[[Node, View], float]) -> None:
        self.key = key

    def select(self, ready: list[Node], view: View) -> list[Node]:
        if not ready:
            return []
        return [max(ready, key=lambda n: self.key(n, view))]
