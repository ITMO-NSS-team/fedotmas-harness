from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from typing import Any

from fedotmas.engine.contract import View


def _wants_view(fn: Callable[..., Any]) -> bool:
    """Whether `fn` takes the `view` second argument. The body is called positionally as
    `(input, view)`, so this is "accepts a second positional argument": true when it has two
    or more positional parameters or a `*args`. True as well when the signature cannot be read
    (a C builtin), so an unintrospectable callable keeps the full contract rather than silently
    losing its view."""
    try:
        params = inspect.signature(fn).parameters
    except (TypeError, ValueError):
        return True
    positional = 0
    for p in params.values():
        if p.kind is p.VAR_POSITIONAL:
            return True
        if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD):
            positional += 1
    return positional >= 2


def bind_async(
    fn: Callable[..., Awaitable[Any]],
) -> Callable[[Any, View], Awaitable[Any]]:
    """Adapt an async leaf body to the `(input, view)` call contract: pass it through when it
    wants `view`, else wrap it to drop the argument."""
    if _wants_view(fn):
        return fn

    async def invoke(input: Any, view: View) -> Any:
        return await fn(input)

    return invoke


def bind_pred(fn: Callable[..., Any]) -> Callable[[Any, View], Any]:
    """Adapt a sync selector or predicate to the `(state, view)` call contract: pass it through
    when it wants `view`, else wrap it to drop the argument."""
    if _wants_view(fn):
        return fn
    return lambda state, view: fn(state)
