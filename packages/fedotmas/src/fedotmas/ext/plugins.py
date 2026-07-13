from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from fedotmas.engine.plugin import Plugin

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from fedotmas.engine.contract import Fact, Node, Result, View

    NodeCall = Callable[[list[Fact], View], Awaitable[Result]]


class Retry(Plugin):
    """Re-run the node up to `times` attempts (at least 1). `on` narrows what is retried;
    anything else, and the last attempt's exception, propagates — retrying a deterministic
    bug only repeats its side effects. Holds no per-node state, so one instance is safe
    across a concurrent gather."""

    def __init__(
        self,
        times: int,
        *,
        on: type[Exception] | tuple[type[Exception], ...] = Exception,
    ) -> None:
        if times < 1:
            raise ValueError(f"Retry needs times >= 1, got {times}")
        self.times = times
        self.on = on

    async def around_node(
        self, node: Node, input: list[Fact], view: View, call: NodeCall
    ) -> Result:
        for _ in range(self.times - 1):
            try:
                return await call(input, view)
            except self.on:
                pass
        return await call(input, view)


class Timeout(Plugin):
    """Bound each node call to `seconds`, raising `TimeoutError` past it (which the executor
    turns into that node's error fact)."""

    def __init__(self, seconds: float) -> None:
        self.seconds = seconds

    async def around_node(
        self, node: Node, input: list[Fact], view: View, call: NodeCall
    ) -> Result:
        return await asyncio.wait_for(call(input, view), self.seconds)
