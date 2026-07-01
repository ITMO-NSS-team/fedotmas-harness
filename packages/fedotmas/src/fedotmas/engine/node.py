from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from fedotmas.engine.contract import Card, Kind, Node, Result, View

Invoke = Callable[[Any, View], Awaitable[Result]]
Trigger = Callable[[View], bool]


class _FnNode:
    def __init__(
        self,
        fn: Invoke,
        name: str,
        reads: str,
        trigger: Trigger,
        meta: dict[str, Any],
        kind: str,
        writes: list[str],
        params: dict[str, Any],
        system: Any,
    ) -> None:
        self.name = name
        self.reads = reads
        self._fn = fn
        self._trigger = trigger
        self._meta = meta
        self._kind = kind
        self._writes = writes
        self._params = params
        self._system = system

    def trigger(self, view: View) -> bool:
        return self._trigger(view)

    async def invoke(self, input: Any, view: View) -> Result:
        return await self._fn(input, view)

    def describe(self) -> Card:
        return Card(
            name=self.name,
            description=self._fn.__doc__ or "",
            meta=self._meta,
            kind=self._kind,
            reads=self.reads.split(),
            writes=self._writes,
            params=self._params,
            system=self._system,
        )


def as_node(
    fn: Invoke,
    *,
    name: str,
    reads: str = "",
    trigger: Trigger | None = None,
    meta: dict[str, Any] | None = None,
    kind: str = Kind.ACTION,
    writes: list[str] | None = None,
    params: dict[str, Any] | None = None,
    system: Any = None,
) -> Node:
    """Wrap an async (input, view) -> Result function as a Node. `reads` holds one or more
    whitespace-separated fact patterns: it is the input the executor matches for the node and
    the node's re-fire identity (see Node). The default trigger is "every reads pattern has a
    match"; with empty reads it is "never", so a node without reads needs an explicit
    `trigger` to fire at all (and then fires at most once per run).

    `kind`, `writes`, `params`, `system` are the node's declarative self-portrait for its Card
    and never touch execution; `writes` defaults to the node's own name, so only the kinds that
    write elsewhere (alias, rule, branch routing, loop) pass it explicitly. `system` is a live
    sub-system a walker recurses into (nest, loop).
    """
    if trigger is not None:
        trig = trigger
    elif reads:
        patterns = reads.split()
        trig = lambda view: all(view.exists(p) for p in patterns)  # noqa: E731
    else:
        trig = lambda view: False  # noqa: E731
    return _FnNode(
        fn,
        name,
        reads,
        trig,
        meta or {},
        kind,
        [name] if writes is None else writes,
        params or {},
        system,
    )
