from __future__ import annotations

from typing import Any, Literal, TypeVar, overload

from fedotmas.engine.contract import Node, View
from fedotmas.ext import Ctx, Flow, node_from_fn, render

from fedotmas_llm._llm import LLM, Call
from fedotmas_llm._tools import Tool

A = TypeVar("A")
B = TypeVar("B")


class _LLMAtom(Flow[Any, Any]):
    """A leaf whose body is a prompt over the LLM seam. The backend binds per node or falls
    back to the run-scoped "llm" binding (``bind={"llm": ...}``); binding neither is a
    compile-time error."""

    def __init__(
        self,
        name: str,
        *,
        prompt: str,
        input: str | None,
        returns: Any,
        llm: LLM | None,
        labels: list[str] | None = None,
        tools: list[Tool] | None = None,
    ) -> None:
        self._name = name
        self._prompt = prompt
        self._input = input
        self._returns = returns
        self._llm = llm
        self._labels = labels
        self._tools = tools

    def _build(self, ctx: Ctx, entry: str) -> tuple[list[Node], str]:
        llm = self._llm or ctx.bindings.get("llm")
        if llm is None:
            raise ValueError(
                f"node {self._name!r} has no llm bound: pass llm= on the node or the "
                'run-scoped default bind={"llm": ...} at .run()/.system()'
            )
        name, prompt, template = self._name, self._prompt, self._input
        returns, labels, tools = self._returns, self._labels, self._tools

        async def invoke(value: Any, view: View) -> Any:
            content = render(template, value, view, name) if template else value
            call = Call(prompt, content, returns=returns, tools=tuple(tools or ()))
            reply = await llm.complete(call, view)
            if labels is not None and reply not in labels:
                raise ValueError(f"agent {name!r} returned {reply!r}, not in {labels}")
            return reply

        out = ctx.fresh(name)
        return [node_from_fn(out, invoke, entry, out)], out


@overload
def agent(
    name: str,
    *,
    prompt: str,
    input: str | None = ...,
    llm: LLM | None = ...,
    tools: list[Tool] | None = ...,
) -> Flow[str, str]: ...
@overload
def agent(
    name: str,
    *,
    prompt: str,
    takes: type[A],
    returns: type[B],
    input: str | None = ...,
    llm: LLM | None = ...,
    tools: list[Tool] | None = ...,
) -> Flow[A, B]: ...
@overload
def agent(
    name: str,
    *,
    prompt: str,
    labels: list[str],
    input: str | None = ...,
    takes: type[A] = ...,
    llm: LLM | None = ...,
    tools: list[Tool] | None = ...,
) -> Flow[A, str]: ...
def agent(
    name: str,
    *,
    prompt: str,
    input: str | None = None,
    takes: type = str,
    returns: type = str,
    labels: list[str] | None = None,
    llm: LLM | None = None,
    tools: list[Tool] | None = None,
) -> Flow[Any, Any]:
    """Lift a prompt into an LLM agent: a Flow atom whose body is data, not code. Always a
    model call; the deterministic counterpart is fedotmas.action.

    `prompt` is the static system prompt. `input` is an optional template for what the model
    sees, rendered over the node's input (dict keys or model fields, store tags as fallback,
    `{input}` for the whole value); without it the input is passed through unchanged. Declare
    takes/returns to type the boundary; a structured backend produces the `returns` type
    directly. `labels` makes the agent a classifier: the output is one label from the set,
    constrained at the backend via a Literal and validated regardless, the shape that drives
    branch when the route is the model's choice. To thread a dict state, compose the result:
    `agent(..., takes=dict, returns=...).into("key")` puts the reply under one key, `.merge()`
    folds a structured reply's fields in. `tools` are the tools the model may call, a mix of
    FunctionTool (a local callable) and MCPTool (a server url); they reach the backend only
    when present, so declaring tools requires a backend that accepts them. The backend binds
    via `llm` here or the run-scoped `bind={"llm": ...}`; neither bound fails at compile time.

    Example:
        draft = agent("draft", prompt="Write a haiku about {topic}.")
        route = agent("route", prompt="Pick a desk.", labels=["sales", "support"])
    """
    if labels is not None:
        if returns is not str:
            raise ValueError(
                f"agent {name!r}: labels= fixes the output to one label; it does not "
                "combine with returns="
            )
        # built via __getitem__ because the labels are runtime data, not a static type form
        lit = Literal.__getitem__(tuple(labels))
        return _LLMAtom(
            name,
            prompt=prompt,
            input=input,
            returns=lit,
            llm=llm,
            labels=labels,
            tools=tools,
        )
    return _LLMAtom(
        name, prompt=prompt, input=input, returns=returns, llm=llm, tools=tools
    )
