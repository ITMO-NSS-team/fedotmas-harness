from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from fedotmas.engine.contract import View

from fedotmas_llm._tools import Tool


@dataclass(frozen=True)
class Call:
    """The request a node hands the LLM seam: the static system `prompt`, the already-rendered
    `input` the model sees, the declared `returns` type (a type or a Literal of labels), and the
    node's `tools`. It is the proposal a meta-agent authors. `view` travels beside a Call, not in
    it, because it is the run's live store handle, not request data."""

    prompt: str
    input: Any
    returns: Any = str
    tools: tuple[Tool, ...] = ()


@dataclass(frozen=True)
class Usage:
    """The meters a backend accumulates over its calls. Summable, so a proxy or a report can fold
    several backends' totals into one."""

    input_tokens: int = 0
    output_tokens: int = 0
    requests: int = 0

    def __add__(self, other: Usage) -> Usage:
        return Usage(
            self.input_tokens + other.input_tokens,
            self.output_tokens + other.output_tokens,
            self.requests + other.requests,
        )


class LLM(Protocol):
    """The LLM call seam: turn a node's Call into a value. Anything with this method (a provider
    client, a stub, a test fake) plugs in via a node's binding, so the engine never imports a
    provider. The prompt travels in the Call, which is what lets a meta-agent author it while the
    backend stays swappable; `Call.returns` lets a structured backend produce the declared type
    directly, and `Call.tools` are forwarded to a tool-capable backend. `view` is the run's store
    handle, passed beside the Call for a backend that reads shared state; most ignore it."""

    async def complete(self, call: Call, view: View) -> Any: ...
