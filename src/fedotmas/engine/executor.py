"""The engine: Executor protocol and ReactiveExecutor, the single superstep (BSP) loop."""

from __future__ import annotations

import asyncio
import traceback
from collections.abc import AsyncIterator, Iterable
from typing import Literal, Protocol

from fedotmas.engine.contract import Fact, Status, View
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


def _matched(view: View, reads: str) -> list[Fact]:
    return [f for pattern in reads.split() for f in view.query(pattern)]


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
        store.commit(
            [
                f if f.producer else f.model_copy(update={"producer": "seed"})
                for f in seed
            ]
        )
        fired: set[tuple[str, frozenset[tuple[str, int]]]] = set()
        step = 0
        while True:
            view = store.snapshot()
            ready = []
            matched: dict[str, tuple[list[Fact], tuple]] = {}
            for node in system.nodes:
                if not node.trigger(view):
                    continue
                facts = _matched(view, node.reads) if node.reads else []
                mkey = (node.name, frozenset(f.key for f in facts))
                if mkey in fired:
                    continue
                ready.append(node)
                matched[node.name] = (facts, mkey)
            ready = active.select(ready, view)
            if not ready:
                yield StepReport(step, [], [])
                return
            results = await asyncio.gather(
                *(node.invoke(matched[node.name][0], view) for node in ready),
                return_exceptions=True,
            )
            writes: list[Fact] = []
            errors: list[Fact] = []
            for node, result in zip(ready, results):
                fired.add(matched[node.name][1])
                if isinstance(result, BaseException):
                    if not isinstance(result, Exception):
                        raise result
                    errors.append(_error_fact(node.name, str(result), step, result))
                    continue
                if result.status is Status.ERROR:
                    errors.append(
                        _error_fact(node.name, result.error or "", step, None)
                    )
                writes.extend(_stamp(result.writes, node.name, step))
            store.commit([*writes, *errors])
            report = StepReport(step, [node.name for node in ready], writes, errors)
            yield report
            if errors and self._halt:
                return
            if terminate is not None and terminate.done(store.snapshot(), report):
                return
            step += 1

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
