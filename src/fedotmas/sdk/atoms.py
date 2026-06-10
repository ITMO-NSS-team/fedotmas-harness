"""The atoms: leaf factories that fill a surface, plus the LLM seam they call.

action lifts a plain async function (the body is code), agent lifts a prompt into an LLM node
(the body is data), decision lifts a prompt into a router over a finite label set. All three
return a Flow[A, B] and compose with the same operators; the model-free action and the
model-aware agent differ only in what fills the leaf, never in how they compose.

An LLM node is fully declarative: strings, types, and keys. `prompt` is the static system
prompt. `input` is a template for what the model sees, rendered over the node's input (dict
keys or model fields) with store tags as fallback, so a stateful node picks what it feeds the
model without code. `into` and `merge` put the reply back into a dict state, which is what
lets the same atoms fill loops, swarms, and chats that thread state, not only stateless
chains. None of these accept a callable; action is the escape hatch when behavior must be code.

The LLM seam lives here with its only callers. The SDK never imports a provider: a backend is
injected via `llm` on the node or as the default at .system()/.run(), anything with a
`complete` method satisfies it, and an unbound node fails at compile time.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from typing import Any, Literal, Protocol, TypeVar, overload

from pydantic import BaseModel

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
    the backend stays swappable. `returns` carries the node's declared output type (a type or
    a Literal of labels), so a backend that supports structured output can produce that type
    directly; a plain-text backend ignores it.
    """

    async def complete(
        self, prompt: str, input: Any, view: View, returns: Any = str
    ) -> Any: ...


class _Scope(Mapping[str, Any]):
    """Template namespace: input fields first, then store tags, then `input` for the whole
    incoming value. Raises KeyError for anything else, so a typo in a template names itself."""

    def __init__(self, value: Any, view: View) -> None:
        self._value = value
        self._view = view

    def __getitem__(self, key: str) -> Any:
        if isinstance(self._value, dict) and key in self._value:
            return self._value[key]
        if isinstance(self._value, BaseModel) and key in type(self._value).model_fields:
            return getattr(self._value, key)
        fact = self._view.get(key)
        if fact is not None:
            return fact.value
        if key == "input":
            return self._value
        raise KeyError(key)

    def __iter__(self) -> Any:
        raise NotImplementedError

    def __len__(self) -> int:
        raise NotImplementedError


def _render(template: str, value: Any, view: View, node: str) -> str:
    try:
        return template.format_map(_Scope(value, view))
    except KeyError as e:
        raise RuntimeError(
            f"node {node!r}: template references {e.args[0]!r}, which is neither an "
            "input field nor a store tag"
        ) from None


def _put_back(value: Any, reply: Any, into: str | None, merge: bool, node: str) -> Any:
    if into is not None:
        if not isinstance(value, dict):
            raise TypeError(
                f"node {node!r}: into= threads a dict state, got {type(value).__name__}"
            )
        return {**value, into: reply}
    if merge:
        patch = reply.model_dump() if isinstance(reply, BaseModel) else reply
        if not isinstance(value, dict) or not isinstance(patch, dict):
            raise TypeError(
                f"node {node!r}: merge= needs a dict state and a structured reply, got "
                f"{type(value).__name__} and {type(reply).__name__}"
            )
        return {**value, **patch}
    return reply


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
        into: str | None,
        merge: bool,
        llm: LLM | None,
        validate: Callable[[Any], None] | None = None,
    ) -> None:
        if into is not None and merge:
            raise ValueError(f"node {name!r}: into= and merge= are mutually exclusive")
        self._name = name
        self._prompt = prompt
        self._input = input
        self._returns = returns
        self._into = into
        self._merge = merge
        self._llm = llm
        self._validate = validate

    def _build(self, ctx: _Ctx, entry: str) -> tuple[list[Agent], str]:
        llm = self._llm or ctx.llm
        if llm is None:
            raise ValueError(
                f"node {self._name!r} has no llm bound: pass llm= on the node or as the "
                "default at .system()/.run()"
            )
        name, prompt, template = self._name, self._prompt, self._input
        returns, into, merge = self._returns, self._into, self._merge
        validate = self._validate

        async def invoke(value: Any, view: View) -> Any:
            content = _render(template, value, view, name) if template else value
            reply = await llm.complete(prompt, content, view, returns=returns)
            if validate is not None:
                validate(reply)
            return _put_back(value, reply, into, merge, name)

        out = ctx.fresh(name)
        return [_action_agent(out, invoke, entry, out)], out


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
    into: str,
    input: str | None = ...,
    returns: type = ...,
    llm: LLM | None = ...,
) -> Flow[dict, dict]: ...
@overload
def agent(
    name: str,
    *,
    prompt: str,
    merge: bool,
    input: str | None = ...,
    returns: type = ...,
    llm: LLM | None = ...,
) -> Flow[dict, dict]: ...
def agent(
    name: str,
    *,
    prompt: str,
    input: str | None = None,
    takes: type = str,
    returns: type = str,
    into: str | None = None,
    merge: bool = False,
    llm: LLM | None = None,
) -> Flow[Any, Any]:
    """Lift a prompt into an LLM node: a Flow atom whose body is data, not code.

    `prompt` is the static system prompt. `input` is an optional template for what the model
    sees, rendered over the node's input (dict keys or model fields, store tags as fallback,
    `{input}` for the whole value); without it the input is passed through unchanged. Declare
    takes/returns to type the boundary; a structured backend produces the `returns` type
    directly. For a node inside stateful composition, `into="key"` writes the reply under that
    key of a dict state and passes the rest through, while `merge=True` folds a structured
    reply's fields into the state; both make the node Flow[dict, dict]. The backend binds via
    `llm` here or via the default at .system()/.run(); neither bound fails at compile time.
    """
    return _LLMAtom(
        name,
        prompt=prompt,
        input=input,
        returns=returns,
        into=into,
        merge=merge,
        llm=llm,
    )


@overload
def decision(
    name: str,
    *,
    prompt: str,
    labels: list[str],
    input: str | None = ...,
    llm: LLM | None = ...,
) -> Flow[str, str]: ...
@overload
def decision(
    name: str,
    *,
    prompt: str,
    labels: list[str],
    takes: type[A],
    input: str | None = ...,
    llm: LLM | None = ...,
) -> Flow[A, str]: ...
def decision(
    name: str,
    *,
    prompt: str,
    labels: list[str],
    input: str | None = None,
    takes: type = str,
    llm: LLM | None = None,
) -> Flow[Any, str]:
    """Lift a prompt into a router: an LLM node that returns one label from a finite set. Like
    agent, but the output is constrained to `labels`: the label set rides to the backend as a
    Literal `returns`, so a structured backend cannot produce anything else, and the reply is
    validated against the set regardless. This is what lets it drive branch when the route is
    chosen by a model rather than by data already in the state.
    """
    # built via __getitem__ because the labels are runtime data, not a static type form
    lit = Literal.__getitem__(tuple(labels))

    def validate(reply: Any) -> None:
        if reply not in labels:
            raise ValueError(f"decision {name!r} returned {reply!r}, not in {labels}")

    return _LLMAtom(
        name,
        prompt=prompt,
        input=input,
        returns=lit,
        into=None,
        merge=False,
        llm=llm,
        validate=validate,
    )
