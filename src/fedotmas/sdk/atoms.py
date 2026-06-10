"""The atoms: leaf factories that fill a surface, plus the LLM seam they call.

action lifts a plain async function (the body is code), agent lifts a prompt into an LLM node
(the body is data), decision lifts a prompt into a router over a finite label set. All three
return a Flow[A, B] and compose with the same operators; the model-free action and the
model-aware agent differ only in what fills the leaf, never in how they compose.

The LLM seam lives here with its only callers. The SDK never imports a provider: a backend is
injected via `llm`, anything with a `complete` method satisfies it, and the binding can be
deferred to compile time.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, Protocol, TypeVar, overload

from fedotmas.adapters import as_agent
from fedotmas.engine.contract import Agent, Fact, Result, View
from fedotmas.sdk.flow import Flow, _Ctx

A = TypeVar("A")
B = TypeVar("B")

ActionFn = Callable[[A, View], Awaitable[B]]


def _action_agent(name: str, fn: ActionFn[Any, Any], reads: str, out: str) -> Agent:
    async def invoke(input: Any, view: View) -> Result:
        value = await fn(view.value(reads) if reads else None, view)
        return Result(writes=[Fact(tag=out, value=value)])

    return as_agent(invoke, name=name, reads=reads)


class _Action(Flow[A, B]):
    def __init__(self, name: str, fn: ActionFn[A, B]) -> None:
        self._name = name
        self._fn = fn

    def _build(self, ctx: _Ctx, entry: str) -> tuple[list[Agent], str]:
        out = ctx.fresh(self._name)
        return [_action_agent(out, self._fn, entry, out)], out


def action(fn: ActionFn[A, B]) -> Flow[A, B]:
    """Lift a plain async function (input, view) -> output into a Flow atom. The body is code
    and the types come from the signature; no model is involved. This is the model-free atom,
    the same arrow shape an agent has but mechanical, so the two compose without distinction.
    """
    return _Action(getattr(fn, "__name__", "action"), fn)


class LLM(Protocol):
    """The LLM call seam: turn a node's prompt and input into a value. It is a parameter of
    agent and decision, not a way into the engine; anything with this method (a provider
    client, a stub, a test fake) plugs in, so the SDK itself never imports a provider. The
    prompt is supplied by the node, which is what lets a meta-agent author the prompt while
    the backend stays swappable. `returns` carries the node's declared output type, so a
    backend that supports structured output can produce that type directly.
    """

    async def complete(
        self, prompt: str, input: Any, view: View, returns: type = str
    ) -> Any: ...


@overload
def agent(
    name: str, *, prompt: str, llm: LLM | None = ..., role: str = ...
) -> Flow[str, str]: ...
@overload
def agent(
    name: str,
    *,
    prompt: str,
    takes: type[A],
    returns: type[B],
    llm: LLM | None = ...,
    role: str = ...,
) -> Flow[A, B]: ...
def agent(
    name: str,
    *,
    prompt: str,
    takes: type = str,
    returns: type = str,
    llm: LLM | None = None,
    role: str = "",
) -> Flow[Any, Any]:
    """Lift a prompt into an LLM node: a Flow atom whose body is the prompt (data, not code)
    and whose backend is supplied via `llm`, the LLM seam. Declare takes/returns to type the
    boundary; with a structured backend the `returns` type is produced directly. role is node
    metadata. The prompt is authored here, so a meta-agent can mint the node textually while
    the backend stays swappable; binding the actual llm can be deferred to compile time.
    """

    async def invoke(input: Any, view: View) -> Any:
        if llm is None:
            raise RuntimeError(f"agent {name!r} has no llm bound")
        return await llm.complete(prompt, input, view, returns=returns)

    return _Action(name, invoke)


@overload
def decision(
    name: str,
    *,
    prompt: str,
    labels: list[str],
    llm: LLM | None = ...,
    role: str = ...,
) -> Flow[str, str]: ...
@overload
def decision(
    name: str,
    *,
    prompt: str,
    labels: list[str],
    takes: type[A],
    llm: LLM | None = ...,
    role: str = ...,
) -> Flow[A, str]: ...
def decision(
    name: str,
    *,
    prompt: str,
    labels: list[str],
    takes: type = str,
    llm: LLM | None = None,
    role: str = "",
) -> Flow[Any, str]:
    """Lift a prompt into a router: an LLM node that returns one label from a finite set. Like
    agent, but the output is constrained to `labels`, which is what lets it drive branch, whose
    selector a meta-agent must express in text rather than as a python callable. Raises if the
    backend returns a label outside the set.
    """

    async def invoke(input: Any, view: View) -> Any:
        if llm is None:
            raise RuntimeError(f"decision {name!r} has no llm bound")
        label = await llm.complete(prompt, input, view)
        if label not in labels:
            raise ValueError(f"decision {name!r} returned {label!r} not in {labels}")
        return label

    return _Action(name, invoke)
