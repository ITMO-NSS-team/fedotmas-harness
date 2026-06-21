from __future__ import annotations

from typing import Any, Protocol

from fedotmas.engine.contract import View


class LLM(Protocol):
    """The LLM call seam: turn a node's prompt and input into a value. Anything with this
    method (a provider client, a stub, a test fake) plugs in via a node's binding, so the
    engine never imports a provider. The prompt is supplied by the node, which is what lets a
    meta-agent author the prompt while the backend stays swappable. `returns` carries the
    node's declared output type (a type or a Literal of labels), so a backend that supports
    structured output can produce that type directly; a plain-text backend ignores it.
    """

    async def complete(
        self, prompt: str, input: Any, view: View, returns: Any = str
    ) -> Any: ...
