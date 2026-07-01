"""DeepEval adapter. Temporarly constant stubs."""

from __future__ import annotations

from typing import Any, get_args

from deepeval.models import DeepEvalBaseLLM

_ANSWER = "0"  # answer stub


class StubModel(DeepEvalBaseLLM):
    """One matrix configuration reduced to a constant: every prompt returns the same answer."""

    def __init__(self, name: str) -> None:
        self.label = name
        self.calls = 0
        self.failures = 0
        self.errors: list[str] = []

    def load_model(self) -> Any:
        return None

    async def a_generate(self, prompt: str) -> str:
        self.calls += 1
        return _ANSWER

    def generate(self, prompt: str, schema: Any = None) -> Any:
        """Answer schemas get a fixed value: 0 for int answers, the first option for
        Literal[str, ...] choices. Any other schema raises, matching how the real model
        signalled deepeval to fall back to its confinement instructions."""
        self.calls += 1
        if schema is None:
            return _ANSWER
        field = schema.model_fields.get("answer")
        annotation = field.annotation if field is not None else None
        options = get_args(annotation)
        if annotation is int:
            return schema(answer=0)
        if options and all(isinstance(o, str) for o in options):
            return schema(answer=options[0])
        raise TypeError(f"unsupported schema {schema.__name__}")

    def batch_generate(self, prompts: list[str]) -> list[str]:
        self.calls += len(prompts)
        return [_ANSWER for _ in prompts]

    def get_model_name(self) -> str:
        return self.label
