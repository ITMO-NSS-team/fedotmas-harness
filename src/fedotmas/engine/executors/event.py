"""Event executor: the blackboard superstep loop."""

from __future__ import annotations

import asyncio
from collections.abc import Iterable

from fedotmas.engine.contract import Fact, Status
from fedotmas.engine.policy import FireAll, Policy
from fedotmas.engine.scheduler import Run, StepReport
from fedotmas.engine.store import Store
from fedotmas.engine.system import System
from fedotmas.engine.terminate import Terminate


def _stamp(facts: Iterable[Fact], producer: str, step: int) -> list[Fact]:
    out = list(facts)
    for f in out:
        f.producer = producer
        f.step = step
    return out


class EventExecutor:
    async def run(
        self,
        system: System,
        store: Store,
        *,
        seed: Iterable[Fact] = (),
        terminate: Terminate | None = None,
        policy: Policy | None = None,
    ) -> Run:
        active = policy or FireAll()
        store.commit(_stamp(seed, "seed", 0))
        fired: set[tuple[str, frozenset[tuple[str, int]]]] = set()
        steps: list[StepReport] = []
        step = 0
        while True:
            view = store.snapshot()
            ready = []
            matched: dict[str, tuple[list[Fact], tuple]] = {}
            for agent in system.agents:
                if not agent.trigger(view):
                    continue
                facts = view.query(agent.reads) if agent.reads else []
                mkey = (agent.name, frozenset(f.key for f in facts))
                if mkey in fired:
                    continue
                ready.append(agent)
                matched[agent.name] = (facts, mkey)
            ready = active.select(ready, view)
            if not ready:
                steps.append(StepReport(step, [], []))
                break
            results = await asyncio.gather(
                *(agent.invoke(matched[agent.name][0], view) for agent in ready)
            )
            writes: list[Fact] = []
            for agent, result in zip(ready, results):
                writes.extend(_stamp(result.writes, agent.name, step))
                fired.add(matched[agent.name][1])
            store.commit(writes)
            report = StepReport(step, [agent.name for agent in ready], writes)
            steps.append(report)
            if terminate is not None and terminate.done(store.snapshot(), report):
                break
            step += 1
        return Run(Status.OK, steps, store.snapshot())
