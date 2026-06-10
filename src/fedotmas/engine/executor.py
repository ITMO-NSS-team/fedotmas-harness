"""The engine: Executor protocol and ReactiveExecutor, the single superstep (BSP) loop."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterable
from typing import Protocol

from fedotmas.engine.contract import Fact, Status
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
    out = list(facts)
    for f in out:
        f.producer = producer
        f.step = step
    return out


def _error_fact(name: str, message: str, step: int, kind: str = "") -> Fact:
    meta = {"type": kind} if kind else {}
    return Fact(tag=f"error:{name}", value=message, producer=name, step=step, meta=meta)


class ReactiveExecutor:
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
        store.commit(_stamp(seed, "seed", -1))
        fired: set[tuple[str, frozenset[tuple[str, int]]]] = set()
        step = 0
        while True:
            view = store.snapshot()
            ready = []
            matched: dict[str, tuple[list[Fact], tuple]] = {}
            for node in system.nodes:
                if not node.trigger(view):
                    continue
                facts = view.query(node.reads) if node.reads else []
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
                    errors.append(
                        _error_fact(node.name, str(result), step, type(result).__name__)
                    )
                    continue
                if result.status is Status.ERROR:
                    errors.append(_error_fact(node.name, result.error or "", step))
                writes.extend(_stamp(result.writes, node.name, step))
            store.commit([*writes, *errors])
            report = StepReport(step, [node.name for node in ready], writes, errors)
            yield report
            if errors:
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
        status, reason = Status.OK, "terminate"
        if steps and steps[-1].errors:
            status, reason = Status.ERROR, "error"
        elif steps and not steps[-1].fired:
            reason = "quiescence"
        return Run(status, steps, store.snapshot(), reason)
