from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel
from pydantic_ai import Agent

from fedotmas.engine.contract import View


def _as_text(input: Any) -> str:
    if isinstance(input, str):
        return input
    if isinstance(input, BaseModel):
        return input.model_dump_json()
    return json.dumps(input, ensure_ascii=False, default=str)


_METERS = ("input_tokens", "output_tokens", "requests")


class PydanticAI:
    """An LLM backend over pydantic-ai: plug it in wherever a node or run takes `llm`. `model`
    is a pydantic-ai model id (e.g. "openai:gpt-4o"); `settings` pass straight to the Agent.
    `usage` accumulates token and request counts across every call. The non-string input is
    sent as JSON, and `returns` becomes the agent's output_type, so a structured type comes
    back parsed."""

    def __init__(self, model: str, **settings: Any) -> None:
        self._model = model
        self._settings = settings
        # one Agent per (prompt, output type): both are fixed per node, so the cache is stable
        self._agents: dict[tuple[str, Any], Agent] = {}
        self.usage: dict[str, int] = dict.fromkeys(_METERS, 0)

    async def complete(
        self, prompt: str, input: Any, view: View, returns: Any = str
    ) -> Any:
        agent = self._agents.get((prompt, returns))
        if agent is None:
            agent = Agent(
                self._model, output_type=returns, system_prompt=prompt, **self._settings
            )
            self._agents[(prompt, returns)] = agent
        result = await agent.run(_as_text(input))
        used = result.usage
        for key in _METERS:
            self.usage[key] = self.usage.get(key, 0) + (getattr(used, key) or 0)
        return result.output
