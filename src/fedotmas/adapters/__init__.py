"""Extension point: wrap your own framework as a Node (see engine.contract). Helper as_node over a callable."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from fedotmas.engine.contract import Card, Node, Result, View

Invoke = Callable[[Any, View], Awaitable[Result]]
Trigger = Callable[[View], bool]


class _FnNode:
    def __init__(
        self, fn: Invoke, name: str, reads: str, trigger: Trigger, meta: dict[str, Any]
    ) -> None:
        self.name = name
        self.reads = reads
        self._fn = fn
        self._trigger = trigger
        self._meta = meta

    def trigger(self, view: View) -> bool:
        return self._trigger(view)

    async def invoke(self, input: Any, view: View) -> Result:
        return await self._fn(input, view)

    def describe(self) -> Card:
        return Card(name=self.name, description=self._fn.__doc__ or "", meta=self._meta)


def as_node(
    fn: Invoke,
    *,
    name: str,
    reads: str = "",
    trigger: Trigger | None = None,
    meta: dict[str, Any] | None = None,
) -> Node:
    trig = trigger or (lambda view: view.exists(reads) if reads else False)
    return _FnNode(fn, name, reads, trig, meta or {})
