"""DeepEval adapter: a built fedotmas flow plays the model under evaluation."""

from __future__ import annotations

import asyncio
import re
from typing import Any

from deepeval.models import DeepEvalBaseLLM
from fedotmas.sdk import LLM, Flow

_NUM = re.compile(r"-?\d[\d,]*(?:\.\d+)?")


def _last_int(text: str) -> int:
    hits = _NUM.findall(text)
    return int(float(hits[-1].replace(",", ""))) if hits else 0


class CountingLLM:
    """Wraps the LLM seam to count calls per configuration."""

    def __init__(self, inner: LLM) -> None:
        self.inner = inner
        self.calls = 0

    async def complete(
        self, prompt: str, input: Any, view: Any, returns: Any = str
    ) -> Any:
        self.calls += 1
        return await self.inner.complete(prompt, input, view, returns=returns)


class FlowModel(DeepEvalBaseLLM):
    """One matrix configuration: a built preset flow evaluated as a single model."""

    def __init__(self, name: str, flow: Flow[Any, Any], llm: LLM) -> None:
        self.label = name
        self.flow = flow
        self.llm = CountingLLM(llm)

    def load_model(self) -> Any:
        return self.flow

    async def a_generate(self, prompt: str) -> str:
        run = await self.flow.run(prompt, llm=self.llm)
        if not run.ok:
            return f"<failed: {run.reason}>"
        return str(run.value)

    def generate(self, prompt: str, schema: Any = None) -> Any:
        """Numeric answer schemas are extracted from the flow's free-form output; for any
        other schema raise, so deepeval falls back to its confinement instructions."""
        if schema is not None:
            field = schema.model_fields.get("answer")
            if field is None or field.annotation is not int:
                raise TypeError(f"unsupported schema {schema.__name__}")
        text = asyncio.run(self.a_generate(prompt))
        return text if schema is None else schema(answer=_last_int(text))

    def batch_generate(self, prompts: list[str]) -> list[str]:
        async def all_of() -> list[str]:
            return list(await asyncio.gather(*(self.a_generate(p) for p in prompts)))

        return asyncio.run(all_of())

    def get_model_name(self) -> str:
        return self.label
