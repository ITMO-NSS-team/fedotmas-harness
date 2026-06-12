"""The atoms: leaf factories that fill a surface, plus the LLM seam they call.

Two kinds of leaf, split by mechanism: action lifts a plain async function (the body is
code, deterministic, no model), agent lifts a prompt into an LLM node (the body is data).
The word agent always means LLM-backed here; the engine's unit of execution is the Node,
which both compile to. Both return a Flow[A, B] and compose with the same operators.

An LLM node is fully declarative: strings, types, and keys. `prompt` is the static system
prompt. `input` is a template for what the model sees, rendered over the node's input (dict
keys or model fields) with store tags as fallback, so a stateful node picks what it feeds the
model without code. `labels` constrains the output to one of a finite label set (a
classifier, the node shape that drives branch). Putting the reply back into a dict state is
composition, not a call parameter: `.into(key)` and `.merge()` on the resulting flow thread
the state, which is what lets the same atoms fill loops, swarms, and chats. None of these
accept a callable; action is the escape hatch when behavior must be code.

The LLM seam lives here with its only callers. The SDK never imports a provider: a backend is
injected via `llm` on the node or as the default at .system()/.run(), anything with a
`complete` method satisfies it, and an unbound node fails at compile time.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, Literal, Protocol, TypeVar, overload

from fedotmas.engine.contract import Fact, Node, Result, View
from fedotmas.engine.node import as_node
from fedotmas.sdk._template import render
from fedotmas.sdk.flow._algebra import Flow
from fedotmas.sdk.flow._nodes import _Ctx

A = TypeVar("A")
B = TypeVar("B")

ActionFn = Callable[[A, View], Awaitable[B]]


def _action_node(name: str, fn: ActionFn[Any, Any], reads: str, out: str) -> Node:
    async def invoke(input: Any, view: View) -> Result:
        value = await fn(view.value(reads) if reads else None, view)
        return Result(writes=[Fact(tag=out, value=value)])

    return as_node(invoke, name=name, reads=reads)


class _Action(Flow[A, B]):
    def __init__(self, name: str, fn: ActionFn[A, B]) -> None:
        self._name = name
        self._fn = fn

    def _build(self, ctx: _Ctx, entry: str) -> tuple[list[Node], str]:
        out = ctx.fresh(self._name)
        return [_action_node(out, self._fn, entry, out)], out


def action(fn: ActionFn[A, B], *, name: str | None = None) -> Flow[A, B]:
    """Lift a plain async function (input, view) -> output into a Flow atom. The body is code
    and the types come from the signature; no model is involved. This is the model-free atom,
    the same arrow shape an agent has but mechanical, so the two compose without distinction.
    `name` overrides the function's __name__ in traces and error tags; pass it when lifting a
    lambda, which otherwise shows up as <lambda>.
    """
    return _Action(name or getattr(fn, "__name__", "action"), fn)


class LLM(Protocol):
    """The LLM call seam: turn a node's prompt and input into a value. It is a parameter of
    agent, not a way into the engine; anything with this method (a provider client, a stub,
    a test fake) plugs in, so the SDK itself never imports a provider. The prompt is supplied
    by the node, which is what lets a meta-agent author the prompt while the backend stays
    swappable. `returns` carries the node's declared output type (a type or a Literal of
    labels), so a backend that supports structured output can produce that type directly; a
    plain-text backend ignores it.
    """

    async def complete(
        self, prompt: str, input: Any, view: View, returns: Any = str
    ) -> Any: ...


class _LLMAtom(Flow[Any, Any]):
    """A leaf whose body is a prompt over the LLM seam. The backend binds per node or falls
    back to the compile-time default in _Ctx; binding neither is a compile-time error."""

    def __init__(
        self,
        name: str,
        *,
        prompt: str,
        input: str | None,
        returns: Any,
        llm: LLM | None,
        labels: list[str] | None = None,
    ) -> None:
        self._name = name
        self._prompt = prompt
        self._input = input
        self._returns = returns
        self._llm = llm
        self._labels = labels

    def _build(self, ctx: _Ctx, entry: str) -> tuple[list[Node], str]:
        llm = self._llm or ctx.llm
        if llm is None:
            raise ValueError(
                f"node {self._name!r} has no llm bound: pass llm= on the node or as the "
                "default at .system()/.run()"
            )
        name, prompt, template = self._name, self._prompt, self._input
        returns, labels = self._returns, self._labels

        async def invoke(value: Any, view: View) -> Any:
            content = render(template, value, view, name) if template else value
            reply = await llm.complete(prompt, content, view, returns=returns)
            if labels is not None and reply not in labels:
                raise ValueError(f"agent {name!r} returned {reply!r}, not in {labels}")
            return reply

        out = ctx.fresh(name)
        return [_action_node(out, invoke, entry, out)], out


@overload
def agent(
    name: str, *, prompt: str, input: str | None = ..., llm: LLM | None = ...
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
) -> Flow[Any, Any]:
    """Lift a prompt into an LLM agent: a Flow atom whose body is data, not code. Always a
    model call; the deterministic counterpart is action.

    `prompt` is the static system prompt. `input` is an optional template for what the model
    sees, rendered over the node's input (dict keys or model fields, store tags as fallback,
    `{input}` for the whole value); without it the input is passed through unchanged. Declare
    takes/returns to type the boundary; a structured backend produces the `returns` type
    directly. `labels` makes the agent a classifier: the output is one label from the set,
    constrained at the backend via a Literal and validated regardless, the shape that drives
    branch when the route is the model's choice. To thread a dict state, compose the result:
    `agent(..., takes=dict, returns=...).into("key")` puts the reply under one key,
    `.merge()` folds a structured reply's fields in. The backend binds via `llm` here or via
    the default at .system()/.run(); neither bound fails at compile time.
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
            name, prompt=prompt, input=input, returns=lit, llm=llm, labels=labels
        )
    return _LLMAtom(name, prompt=prompt, input=input, returns=returns, llm=llm)
