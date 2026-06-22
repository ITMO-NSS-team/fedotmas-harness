"""DeepEval adapter: a built fedotmas flow plays the model under evaluation."""

from __future__ import annotations

import asyncio
import re
from functools import partial
from typing import Any, get_args

from deepeval.models import DeepEvalBaseLLM
from fedotmas import Flow
from fedotmas_llm import LLM

_NUM = re.compile(r"-?\d[\d,]*(?:\.\d+)?")


def _last_int(text: str) -> int:
    hits = _NUM.findall(text)
    return int(float(hits[-1].replace(",", ""))) if hits else 0


def _last_option(text: str, options: tuple[str, ...]) -> str:
    """Pull the chosen choice letter from free-form CoT. The answer sits on the last line by
    instruction, so prefer a line that looks like an answer (mentions 'answer', is just the
    letter, or has a colon) scanning from the end — this dodges the lowercase 'a' that English
    prose litters everywhere. Fall back to the last standalone letter anywhere."""
    token = re.compile(rf"(?i)\b({'|'.join(re.escape(o) for o in options)})\b")
    canon = {o.lower(): o for o in options}
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    for line in reversed(lines):
        hits = token.findall(line)
        if hits and ("answer" in line.lower() or ":" in line or len(line) <= 4):
            return canon[hits[-1].lower()]
    hits = token.findall(text)
    return canon[hits[-1].lower()] if hits else options[0]


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
        self.failures = 0
        self.errors: list[str] = []

    def load_model(self) -> Any:
        return self.flow

    async def a_generate(self, prompt: str) -> str:
        run = await self.flow.run(prompt, bind={"llm": self.llm})
        if not run.ok:
            self.failures += 1
            detail = str(run.errors[0].value) if run.errors else run.reason
            self.errors.append(detail)
            return f"<failed: {detail}>"
        return str(run.value)

    def generate(self, prompt: str, schema: Any = None) -> Any:
        """Answer schemas are extracted from the flow's free-form output: the last number
        for int answers, the last standalone option for Literal[str, ...] choices. Any
        other schema raises BEFORE the flow runs, so deepeval falls back to its
        confinement instructions without spending llm calls."""
        extract = None
        if schema is not None:
            field = schema.model_fields.get("answer")
            annotation = field.annotation if field is not None else None
            options = get_args(annotation)
            if annotation is int:
                extract = _last_int
            elif options and all(isinstance(o, str) for o in options):
                extract = partial(_last_option, options=options)
            else:
                raise TypeError(f"unsupported schema {schema.__name__}")
        text = asyncio.run(self.a_generate(prompt))
        if extract is None:
            return text
        # error text may contain digits or letters; never mine an answer out of it
        return schema(answer=extract("" if text.startswith("<failed") else text))

    def batch_generate(self, prompts: list[str]) -> list[str]:
        async def all_of() -> list[str]:
            return list(await asyncio.gather(*(self.a_generate(p) for p in prompts)))

        return asyncio.run(all_of())

    def get_model_name(self) -> str:
        return self.label
