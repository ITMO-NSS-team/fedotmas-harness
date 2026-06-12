"""pydantic-ai as the default LLM backend, wrapped into the LLM seam.

A PydanticAI holds a provider model handle. complete builds a pydantic-ai Agent with the
node's prompt as system prompt and returns as output_type, so a typed agent atom gets
structured output for free: the boundary stays typed all the way to the model. Agents are
cached by (prompt, returns), which are constant per node, so the model is resolved once
rather than on every call. The core never imports this module; it is one concrete
implementation of the seam, gated by the llm extra (pip install fedotmas[llm]). Wrap any
other framework the same way to swap it out.
"""

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


class PydanticAI:
    def __init__(self, model: str, **settings: Any) -> None:
        self._model = model
        self._settings = settings
        self._agents: dict[tuple[str, Any], Agent] = {}

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
        return result.output
