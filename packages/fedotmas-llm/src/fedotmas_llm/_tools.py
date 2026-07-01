from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class FunctionTool:
    """A local callable exposed to the model. The fn is opaque code; only the name is data, so
    the body is injected at assembly while the name identifies the tool."""

    name: str
    fn: Callable[..., Any]


@dataclass(frozen=True)
class MCPTool:
    """An MCP server exposed to the model, addressed by url. Pure data, so it needs no registry
    to reconstruct (blueprint round-trip of tools is not wired yet; see the serialize plan)."""

    url: str


Tool = FunctionTool | MCPTool
