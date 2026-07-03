from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class FunctionTool:
    """A local callable exposed to the model."""

    name: str
    fn: Callable[..., Any]


@dataclass(frozen=True)
class MCPTool:
    """An MCP server exposed to the model, addressed by url."""

    url: str


Tool = FunctionTool | MCPTool
