"""The engine: Executor protocol and ReactiveExecutor, the single superstep (BSP) loop."""

from __future__ import annotations

import asyncio
import traceback
from collections.abc import AsyncIterator, Iterable
from typing import Literal, NamedTuple, Protocol

from fedotmas.engine.contract import Fact, Key, Node, Status, View
from fedotmas.engine.policy import FireAll, Policy
from fedotmas.engine.report import Run, StepReport
from fedotmas.engine.store import Store
from fedotmas.engine.system import System
from fedotmas.engine.terminate import Terminate


class Executor(Protocol):
    def stream(
        self,
        system: System,
        store: Store,
        *,
        seed: Iterable[Fact] = (),
        terminate: Terminate | None = None,
        policy: Policy | None = None,
    ) -> AsyncIterator[StepReport]: ...

    async def run(
        self,
        system: System,
        store: Store,
        *,
        seed: Iterable[Fact] = (),
        terminate: Terminate | None = None,
        policy: Policy | None = None,
    ) -> Run: ...


def _stamp(facts: Iterable[Fact], producer: str, step: int) -> list[Fact]:
    return [f.model_copy(update={"producer": producer, "step": step}) for f in facts]


def _seed(facts: Iterable[Fact], step: int) -> list[Fact]:
    """Default-stamp seed facts, keeping anything set explicitly. An unset step lands just
    before the store clock: on a fresh store that is the classic -1, on a re-run it is a
    fresh key instead of a collision with the previous run's seeds."""
    return [
        f.model_copy(
            update={
                "producer": f.producer or "seed",
                "step": f.step if f.step != -1 else step,
            }
        )
        for f in facts
    ]


def _matched(view: View, reads: str) -> list[Fact]:
    return [f for pattern in reads.split() for f in view.query(pattern)]


class _Armed(NamedTuple):
    node: Node
    input: list[Fact]
    key: frozenset[Key]


def _ready(
    system: System, view: View, last_input: dict[str, frozenset[Key]]
) -> list[_Armed]:
    """Nodes whose trigger holds and whose matched input differs from the one they last fired
    on. The store is append-only, so a node's matched set only ever grows; remembering the
    last set per node is enough to fire exactly once per distinct input."""
    armed = []
    for node in system.nodes:
        if not node.trigger(view):
            continue
        facts = _matched(view, node.reads) if node.reads else []
        key = frozenset(f.key for f in facts)
        if last_input.get(node.name) == key:
            continue
        armed.append(_Armed(node, facts, key))
    return armed


def _error_fact(name: str, message: str, step: int, exc: Exception | None) -> Fact:
    meta = {}
    if exc is not None:
        meta = {
            "type": type(exc).__name__,
            "traceback": "".join(traceback.format_exception(exc)),
        }
    return Fact(tag=f"error:{name}", value=message, producer=name, step=step, meta=meta)


class ReactiveExecutor:
    """The superstep loop. `halt_on_error` (default True) ends the run on the first failed
    node; with False the error is still committed as a fact and reported, but the rest of the
    system keeps running and the Run carries Status.ERROR at the end."""

    def __init__(self, *, halt_on_error: bool = True) -> None:
        self._halt = halt_on_error

    async def stream(
        self,
        system: System,
        store: Store,
        *,
        seed: Iterable[Fact] = (),
        terminate: Terminate | None = None,
        policy: Policy | None = None,
    ) -> AsyncIterator[StepReport]:
        active = policy or FireAll()
        store.commit(_seed(seed, store.next_step() - 1))
        last_input: dict[str, frozenset[Key]] = {}
        index = 0
        while True:
            view = store.snapshot()
            step = store.next_step()
            armed = _ready(system, view, last_input)
            chosen = {n.name for n in active.select([a.node for a in armed], view)}
            armed = [a for a in armed if a.node.name in chosen]
            if not armed:
                yield StepReport(step, index, [], [])
                return
            results = await asyncio.gather(
                *(a.node.invoke(a.input, view) for a in armed),
                return_exceptions=True,
            )
            writes: list[Fact] = []
            errors: list[Fact] = []
            for a, result in zip(armed, results):
                last_input[a.node.name] = a.key
                if isinstance(result, BaseException):
                    if not isinstance(result, Exception):
                        raise result
                    errors.append(_error_fact(a.node.name, str(result), step, result))
                    continue
                if result.status is Status.ERROR:
                    errors.append(
                        _error_fact(a.node.name, result.error or "", step, None)
                    )
                writes.extend(_stamp(result.writes, a.node.name, step))
            store.commit([*writes, *errors])
            report = StepReport(
                step, index, [a.node.name for a in armed], writes, errors
            )
            yield report
            if errors and self._halt:
                return
            if terminate is not None and terminate.done(store.snapshot(), report):
                return
            index += 1

    async def run(
        self,
        system: System,
        store: Store,
        *,
        seed: Iterable[Fact] = (),
        terminate: Terminate | None = None,
        policy: Policy | None = None,
    ) -> Run:
        steps = [
            report
            async for report in self.stream(
                system, store, seed=seed, terminate=terminate, policy=policy
            )
        ]
        status = Status.ERROR if any(s.errors for s in steps) else Status.OK
        last = steps[-1]
        if self._halt and last.errors:
            reason: Literal["terminate", "quiescence", "error"] = "error"
        elif not last.fired:
            reason = "quiescence"
        else:
            reason = "terminate"
        return Run(status, steps, store.snapshot(), reason)
