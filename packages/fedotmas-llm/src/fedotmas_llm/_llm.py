from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from fedotmas.engine.contract import View

from fedotmas_llm._tools import Tool


@dataclass(frozen=True)
class Call:
    """The request a node hands the LLM seam."""

    prompt: str
    input: Any
    returns: Any = str
    tools: tuple[Tool, ...] = ()


@dataclass(frozen=True)
class Usage:
    """The meters a backend accumulates over its calls."""

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
    """The LLM call protocl for the engine that turn a node's Call into a value."""

    async def complete(self, call: Call, view: View) -> Any: ...
