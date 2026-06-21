from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

from fedotmas._inject import bind_async
from fedotmas.engine.contract import Fact, Node, Result, View
from fedotmas.engine.node import as_node
from fedotmas.flow._algebra import Flow
from fedotmas.flow._nodes import Ctx

A = TypeVar("A")
B = TypeVar("B")

# A leaf body of either arity: `async (input)` or `async (input, view)`. The union keeps both
# forms typed, so A/B (hence Flow[A, B]) are inferred from the signature whichever you write;
# _inject.bind_async adapts the one-arg form to the engine's (input, view) contract.
ActionFn = Callable[[A], Awaitable[B]] | Callable[[A, View], Awaitable[B]]
_BoundFn = Callable[
    [Any, View], Awaitable[Any]
]  # the adapted body, always (input, view)


def node_from_fn(name: str, fn: _BoundFn, reads: str, out: str) -> Node:
    """Wrap an `(input, view) -> value` body as an engine Node: read `reads` (or None when
    empty), run the body, write the result under `out`. The shared leaf builder behind action
    and any custom node-kind authored through the ext surface."""

    async def invoke(input: Any, view: View) -> Result:
        value = await fn(view.value(reads) if reads else None, view)
        return Result(writes=[Fact(tag=out, value=value)])

    return as_node(invoke, name=name, reads=reads)


class _Action(Flow[A, B]):
    def __init__(self, name: str, fn: _BoundFn) -> None:
        self._name = name
        self._fn = fn

    def _build(self, ctx: Ctx, entry: str) -> tuple[list[Node], str]:
        out = ctx.fresh(self._name)
        return [node_from_fn(out, self._fn, entry, out)], out


def action(fn: ActionFn[A, B], *, name: str | None = None) -> Flow[A, B]:
    """Lift a plain async function into a Flow atom. The body is code and the types come from
    the signature; no model is involved. This is the model-free atom, the same arrow shape an
    agent has but mechanical, so the two compose without distinction. The signature is
    `async (input) -> output`, or `async (input, view) -> output` when the body needs the
    read-only store; the trailing `view` is optional and supplied only when declared. `name`
    overrides the function's __name__ in traces and error tags; pass it when lifting a lambda,
    which otherwise shows up as <lambda>.

    Example:
        async def fetch(url: str) -> str:
            return await client.get(url)

        get = action(fetch)  # Flow[str, str]
    """
    return _Action(name or getattr(fn, "__name__", "action"), bind_async(fn))
