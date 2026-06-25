from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

from fedotmas.engine.contract import Fact, Kind, Node, Result, Status, View
from fedotmas.engine.executor import ReactiveExecutor
from fedotmas.engine.node import as_node
from fedotmas.engine.report import Run
from fedotmas.engine.store import Store
from fedotmas.engine.system import System
from fedotmas.engine.terminate import Terminate

if TYPE_CHECKING:
    from collections.abc import Mapping


@dataclass
class Ctx:
    bindings: Mapping[str, Any] = field(default_factory=dict)
    n: int = 0

    def fresh(self, hint: str) -> str:
        self.n += 1
        return f"{hint}#{self.n}"


def _collect_node(name: str, srcs: list[str], out: str) -> Node:
    async def invoke(input: Any, view: View) -> Result:
        return Result(writes=[Fact(tag=out, value=[view.value(s) for s in srcs])])

    return as_node(
        invoke,
        name=name,
        reads=" ".join(srcs),
        kind=Kind.GATHER,
        params={"srcs": srcs},
    )


def _alias_node(
    src: str, out: str, name: str | None = None, kind: str = Kind.ALIAS
) -> Node:
    async def invoke(input: Any, view: View) -> Result:
        return Result(writes=[Fact(tag=out, value=view.value(src))])

    return as_node(
        invoke, name=name or f"alias:{out}", reads=src, kind=kind, writes=[out]
    )


def _into_node(name: str, state_src: str, reply_src: str, key: str) -> Node:
    """Thread a dict state past a step: the reply lands under `key`, the other keys pass
    through unchanged."""

    async def invoke(input: Any, view: View) -> Result:
        state = view.value(state_src)
        if not isinstance(state, dict):
            raise TypeError(
                f"{name!r}: .into() threads a dict state, got {type(state).__name__}"
            )
        return Result(
            writes=[Fact(tag=name, value={**state, key: view.value(reply_src)})]
        )

    return as_node(
        invoke,
        name=name,
        reads=f"{state_src} {reply_src}",
        kind=Kind.INTO,
        params={"key": key, "state": state_src, "reply": reply_src},
    )


def _merge_node(name: str, state_src: str, reply_src: str) -> Node:
    """Thread a dict state past a step: the structured reply's fields fold into the state
    (a BaseModel reply is dumped first)."""

    async def invoke(input: Any, view: View) -> Result:
        state = view.value(state_src)
        reply = view.value(reply_src)
        patch = reply.model_dump() if isinstance(reply, BaseModel) else reply
        if not isinstance(state, dict) or not isinstance(patch, dict):
            raise TypeError(
                f"{name!r}: .merge() needs a dict state and a structured reply, got "
                f"{type(state).__name__} and {type(reply).__name__}"
            )
        return Result(writes=[Fact(tag=name, value={**state, **patch})])

    return as_node(
        invoke,
        name=name,
        reads=f"{state_src} {reply_src}",
        kind=Kind.MERGE,
        params={"state": state_src, "reply": reply_src},
    )


def _inner_guard(run: Run, out: str, what: str) -> None:
    """Surface an inner run's failure as this node's failure, so the outer engine records it
    as an error fact instead of silently writing None."""
    if run.status is Status.ERROR:
        msgs = "; ".join(
            f"{e.producer}: {e.value}" for s in run.steps for e in s.errors
        )
        raise RuntimeError(f"{what}: inner system failed ({msgs})")
    if not run.view.exists(out):
        raise RuntimeError(
            f"{what}: inner system stopped ({run.reason}) before producing {out!r}"
        )


def _loop_iterate_node(
    name: str,
    body: System,
    body_in: str,
    body_out: str,
    entry: str,
    state: str,
    until: Callable[[Any, View], bool],
    round_term: Terminate,
    until_spec: dict[str, Any],
) -> Node:
    """One round per firing: feed the latest state (the entry fact on round one) into the
    body in a fresh inner store, write its output as the next state version. Re-arms while
    `until` has not yet cleared on the latest state."""

    async def invoke(input: Any, view: View) -> Result:
        seen = view.query(f"{state}:*")
        src = seen[-1].value if seen else (view.value(entry) if entry else None)
        run = await ReactiveExecutor().run(
            body, Store(), seed=[Fact(tag=body_in, value=src)], terminate=round_term
        )
        _inner_guard(run, body_out, f"loop {name!r} round {len(seen) + 1}")
        return Result(
            writes=[
                Fact(tag=f"{state}:{len(seen) + 1}", value=run.view.value(body_out))
            ]
        )

    def trigger(view: View) -> bool:
        seen = view.query(f"{state}:*")
        if not seen:
            return view.exists(entry) if entry else True
        return not until(seen[-1].value, view)

    return as_node(
        invoke,
        name=f"{name}:iter",
        reads=f"{state}:*",
        trigger=trigger,
        kind=Kind.LOOP_ITER,
        writes=[f"{state}:*"],
        params={"until": dict(until_spec)},
        system=body,
    )


def _loop_finish_node(
    name: str,
    state: str,
    out: str,
    until: Callable[[Any, View], bool],
    until_spec: dict[str, Any],
) -> Node:
    """Copy the final state version to the loop's output once `until` clears; fires once,
    guarded by the output not existing yet."""

    async def invoke(input: Any, view: View) -> Result:
        return Result(writes=[Fact(tag=out, value=view.query(f"{state}:*")[-1].value)])

    def trigger(view: View) -> bool:
        seen = view.query(f"{state}:*")
        return bool(seen) and until(seen[-1].value, view) and not view.exists(out)

    return as_node(
        invoke,
        name=f"{name}:done",
        reads=f"{state}:*",
        trigger=trigger,
        kind=Kind.LOOP_DONE,
        writes=[out],
        params={"until": dict(until_spec)},
    )
