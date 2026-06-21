from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any

from fedotmas.engine.contract import View
from fedotmas.ext import Rule, render

from fedotmas_llm._llm import LLM

_BoundFn = Callable[[Any, View], Awaitable[Any]]


@dataclass
class PromptRule(Rule):
    """A blackboard rule whose body is a prompt over the LLM seam, the reactive counterpart to
    fedotmas.Rule's code body and the same minimal pair as agent to action. `prompt` is the
    static system prompt; `input` is an optional template for what the model sees, rendered over
    the read fact; `returns` its output type. It binds its backend via `llm` here or the
    run-scoped `bind={"llm": ...}`; reads/writes/when/meta behave exactly as on a code Rule.

    Example:
        draft = PromptRule(name="draft", reads="topic", writes="draft", prompt="Draft it.")
        check = PromptRule(name="check", reads="draft", writes="report", prompt="Review it.")
        board = blackboard(draft, check)
        out = await board.run({"topic": "tea"}, goal="report", bind={"llm": backend})
    """

    prompt: str | None = None
    input: str | None = None
    returns: Any = str
    llm: LLM | None = None

    def _validate(self) -> None:
        if self.prompt is None:
            raise ValueError(f"rule {self.name!r}: prompt= is required")
        if self.fn is not None:
            raise ValueError(f"rule {self.name!r}: a prompt rule takes no fn=")
        self._check_common()

    def _body(self, bind: Mapping[str, Any]) -> _BoundFn:
        llm = self.llm or bind.get("llm")
        if llm is None:
            raise ValueError(
                f"rule {self.name!r} has no llm bound: pass llm= on the rule or the "
                'run-scoped default bind={"llm": ...}'
            )
        name, prompt, template, returns = (
            self.name,
            self.prompt,
            self.input,
            self.returns,
        )
        assert prompt is not None

        async def step(value: Any, view: View) -> Any:
            content = render(template, value, view, name) if template else value
            return await llm.complete(prompt, content, view, returns=returns)

        return step
