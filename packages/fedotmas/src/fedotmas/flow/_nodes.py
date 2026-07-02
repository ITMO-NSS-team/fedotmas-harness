from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

from fedotmas._addressing import Branch, Loop, alias, build_id
from fedotmas._condition import Predicate, spec_of
from fedotmas.engine.contract import Fact, Kind, Node, Result, Status, View
from fedotmas.engine.executor import ReactiveExecutor
from fedotmas.engine.node import as_node
from fedotmas.engine.report import Run
from fedotmas.engine.store import Store
from fedotmas.engine.system import System
from fedotmas.engine.terminate import Budget, Goal, Terminate, any_of

if TYPE_CHECKING:
    from collections.abc import Mapping


@dataclass
class Ctx:
    bindings: Mapping[str, Any] = field(default_factory=dict)
    n: int = 0

    def fresh(self, hint: str) -> str:
        self.n += 1
        return build_id(hint, self.n)


def _waves(view: View, srcs: list[str], emitted: int) -> list[list[Any]]:
    """The version-aligned waves not yet emitted: wave k pairs the k-th version of every
    source, so a join over a re-entered system never mixes generations. Positional identity
    holds because fire-once-per-distinct-input gives every arm one version per pass."""
    versions = [view.query(s) for s in srcs]
    ready = min(len(v) for v in versions)
    return [[v[k].value for v in versions] for k in range(emitted, ready)]


def _wave_trigger(srcs: list[str], out: str) -> Callable[[View], bool]:
    """Armed only when every source holds a version the output has not consumed yet."""
    return lambda view: all(view.count(s) > view.count(out) for s in srcs)


def _collect_node(name: str, srcs: list[str], out: str) -> Node:
    async def invoke(input: Any, view: View) -> Result:
        emitted = view.count(out)
        return Result(
            writes=[Fact(tag=out, value=w) for w in _waves(view, srcs, emitted)]
        )

    return as_node(
        invoke,
        name=name,
        reads=" ".join(srcs),
        trigger=_wave_trigger(srcs, out),
        kind=Kind.GATHER,
        params={"srcs": srcs},
    )


def _alias_node(
    src: str, out: str, name: str | None = None, kind: str = Kind.ALIAS
) -> Node:
    async def invoke(input: Any, view: View) -> Result:
        return Result(writes=[Fact(tag=out, value=view.value(src))])

    return as_node(invoke, name=name or alias(out), reads=src, kind=kind, writes=[out])


def _into_node(name: str, state_src: str, reply_src: str, key: str) -> Node:
    """Thread a dict state past a step: the reply lands under `key`, the other keys pass
    through unchanged."""

    async def invoke(input: Any, view: View) -> Result:
        writes = []
        for state, reply in _waves(view, [state_src, reply_src], view.count(name)):
            if not isinstance(state, dict):
                raise TypeError(
                    f"{name!r}: .into() threads a dict state, got {type(state).__name__}"
                )
            writes.append(Fact(tag=name, value={**state, key: reply}))
        return Result(writes=writes)

    return as_node(
        invoke,
        name=name,
        reads=f"{state_src} {reply_src}",
        trigger=_wave_trigger([state_src, reply_src], name),
        kind=Kind.INTO,
        params={"key": key, "state": state_src, "reply": reply_src},
    )


def _merge_node(name: str, state_src: str, reply_src: str) -> Node:
    """Thread a dict state past a step: the structured reply's fields fold into the state
    (a BaseModel reply is dumped first)."""

    async def invoke(input: Any, view: View) -> Result:
        writes = []
        for state, reply in _waves(view, [state_src, reply_src], view.count(name)):
            patch = reply.model_dump() if isinstance(reply, BaseModel) else reply
            if not isinstance(state, dict) or not isinstance(patch, dict):
                raise TypeError(
                    f"{name!r}: .merge() needs a dict state and a structured reply, got "
                    f"{type(state).__name__} and {type(reply).__name__}"
                )
            writes.append(Fact(tag=name, value={**state, **patch}))
        return Result(writes=writes)

    return as_node(
        invoke,
        name=name,
        reads=f"{state_src} {reply_src}",
        trigger=_wave_trigger([state_src, reply_src], name),
        kind=Kind.MERGE,
        params={"state": state_src, "reply": reply_src},
    )


def _route_node(
    name: str,
    *,
    route_reads: str,
    entry: str,
    classify: Callable[[Any, View], str] | None,
    label_tag: str,
    ins: dict[str, str],
    select_spec: dict[str, Any],
    cases: list[str],
) -> Node:
    """Route the input to one case's inlet by a label: a python classifier over the value, or
    the label fact a select flow wrote. The case keys and their inlet tags are fixed at build,
    so the route only chooses among them."""

    async def route(input: Any, view: View) -> Result:
        value = view.value(entry) if entry else None
        key = classify(value, view) if classify is not None else view.value(label_tag)
        if key not in ins:
            raise ValueError(
                f"branch {name!r} got label {key!r}, not one of {sorted(ins)}"
            )
        return Result(writes=[Fact(tag=ins[key], value=value)])

    return as_node(
        route,
        name=Branch(name).route,
        reads=route_reads,
        kind=Kind.BRANCH_ROUTE,
        writes=list(ins.values()),
        params={"select": select_spec, "cases": cases},
    )


def _nest_node(
    name: str,
    *,
    system: System,
    entry: str,
    inner_entry: str,
    inner_out: str,
    budget: int | None,
    until: Terminate | None = None,
) -> Node:
    """Run a whole sub-system as one node: seed its own inner store with the outer input, run
    until the inner output exists (or `until`, if given), write it back as one fact. The interior
    stays opaque to the outer engine; a failure surfaces as this node's error. `budget` is the
    inner superstep cap folded into the terminate here, stamped on the Card so the round-trip
    restores the same bound."""
    term: Terminate = until or Goal(lambda v: v.exists(inner_out))
    if budget is not None:
        term = any_of(term, Budget(budget))

    async def invoke(input: Any, view: View) -> Result:
        run = await ReactiveExecutor().run(
            system,
            Store(),
            seed=[Fact(tag=inner_entry, value=view.value(entry) if entry else None)],
            terminate=term,
        )
        _inner_guard(run, inner_out, f"nest {name!r}")
        return Result(writes=[Fact(tag=name, value=run.view.value(inner_out))])

    return as_node(
        invoke,
        name=name,
        reads=entry,
        kind=Kind.NEST,
        params={"entry": inner_entry, "out": inner_out, "budget": budget},
        system=system,
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
    *,
    body: System,
    body_in: str,
    body_out: str,
    entry: str,
    state: str,
    until: Callable[[Any, View], bool],
    pred: Predicate | None,
    budget: int | None,
) -> Node:
    """One round per firing: feed the latest state (the entry fact on round one) into the
    body in a fresh inner store, write its output as the next state version. Re-arms while
    `until` has not yet cleared on the latest state. `budget` is the per-round superstep cap
    folded into the round terminate here, stamped on the Card so the round-trip restores the
    same bound."""
    round_term: Terminate = Goal(lambda v: v.exists(body_out))
    if budget is not None:
        round_term = any_of(round_term, Budget(budget))

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
        name=Loop(name).iter,
        reads=f"{state}:*",
        trigger=trigger,
        kind=Kind.LOOP_ITER,
        writes=[f"{state}:*"],
        params={"until": spec_of(pred), "entry": entry, "budget": budget},
        system=body,
    )


def _loop_finish_node(
    name: str,
    *,
    state: str,
    out: str,
    until: Callable[[Any, View], bool],
    pred: Predicate | None,
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
        name=Loop(name).done,
        reads=f"{state}:*",
        trigger=trigger,
        kind=Kind.LOOP_DONE,
        writes=[out],
        params={"until": spec_of(pred)},
    )
