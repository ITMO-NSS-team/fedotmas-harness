from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from fedotmas.engine.contract import Node, View


class Policy(Protocol):
    """Decides which of the armed nodes actually fire this superstep. The default fires all of
    them; an auction fires one winner."""

    def select(self, ready: list[Node], view: View) -> list[Node]: ...


class FireAll:
    """Fire every armed node. The default: full parallelism each superstep."""

    def select(self, ready: list[Node], view: View) -> list[Node]:
        return ready


class AuctionSelect:
    """Fire only the single highest-scoring node, the contract-net seam. `key` is the bid each
    node makes given the store; ties break on iteration order."""

    def __init__(self, key: Callable[[Node, View], float]) -> None:
        self.key = key

    def select(self, ready: list[Node], view: View) -> list[Node]:
        if not ready:
            return []
        return [max(ready, key=lambda n: self.key(n, view))]
