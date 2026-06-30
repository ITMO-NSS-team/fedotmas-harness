from __future__ import annotations

import json
from typing import Any

from fedotmas.engine.contract import View
from pydantic import BaseModel
from pydantic_ai import Agent, Tool
from pydantic_ai.mcp import MCPToolset

from fedotmas_llm._tools import FunctionTool, MCPTool


def _as_text(input: Any) -> str:
    if isinstance(input, str):
        return input
    if isinstance(input, BaseModel):
        return input.model_dump_json()
    return json.dumps(input, ensure_ascii=False, default=str)


def _split(tools: list[Any]) -> tuple[list[Tool], list[Any]]:
    """Route fedotmas descriptors to pydantic-ai's two slots: FunctionTool -> tools=,
    MCPTool -> toolsets= (MCPToolset reads the transport off the url)."""
    fns = [Tool(t.fn, name=t.name) for t in tools if isinstance(t, FunctionTool)]
    servers = [MCPToolset(t.url) for t in tools if isinstance(t, MCPTool)]
    return fns, servers


def _key(tools: list[Any] | None) -> frozenset[Any]:
    """An order-insensitive cache identity for a tool set. A FunctionTool is keyed by name AND
    the callable itself (same name, different fn = different agent); an MCPTool by url. The
    frozenset holds the fn, so a cached entry keeps its callable alive and identity is stable."""
    if not tools:
        return frozenset()
    return frozenset(
        ("fn", t.name, t.fn) if isinstance(t, FunctionTool) else ("mcp", t.url)
        for t in tools
        if isinstance(t, FunctionTool | MCPTool)
    )


_METERS = ("input_tokens", "output_tokens", "requests")


class PydanticAI:
    """An LLM backend over pydantic-ai Agent."""

    def __init__(self, model: str, **settings: Any) -> None:
        self._model = model
        self._settings = settings
        # caches agents
        self._agents: dict[tuple[str, Any, frozenset[Any]], Agent] = {}
        self.usage: dict[str, int] = dict.fromkeys(_METERS, 0)

    async def complete(
        self,
        prompt: str,
        input: Any,
        view: View,
        returns: Any = str,
        tools: list[Any] | None = None,
    ) -> Any:
        cache_key = (prompt, returns, _key(tools))
        agent = self._agents.get(cache_key)
        if agent is None:
            fns, servers = _split(tools or [])
            agent = Agent(
                self._model,
                output_type=returns,
                system_prompt=prompt,
                tools=fns,
                toolsets=servers,
                **self._settings,
            )
            self._agents[cache_key] = agent
        result = await agent.run(_as_text(input))
        used = result.usage
        for key in _METERS:
            self.usage[key] = self.usage.get(key, 0) + (getattr(used, key) or 0)
        return result.output
