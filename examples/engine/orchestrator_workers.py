"""Orchestrator-Workers (P9): planner decides the subtask count at runtime.

The width is unknown at design time: the planner emits N subtask facts, the worker
maps over whatever is there, the reducer joins. True per-item concurrency would use a
bounded worker pool; here one worker batch-maps the runtime-sized set.
"""

import asyncio

from fedotmas.adapters import as_agent
from fedotmas.engine.contract import Fact, Result, View
from fedotmas.engine.executor import ReactiveExecutor
from fedotmas.engine.store import Store
from fedotmas.engine.system import System
from fedotmas.engine.terminate import Goal

SUBTASKS = ["x", "y", "z"]


async def plan(input: object, view: View) -> Result:
    return Result(writes=[Fact(tag=f"sub:{s}", value=s) for s in SUBTASKS])


async def work(input: object, view: View) -> Result:
    subs = view.query("sub:*")
    return Result(
        writes=[Fact(tag=f"res:{s.value}", value=f"done {s.value}") for s in subs]
    )


async def reduce(input: object, view: View) -> Result:
    done = [r.value for r in view.query("res:*")]
    return Result(writes=[Fact(tag="summary", value=", ".join(done))])


async def main() -> None:
    system = System(
        agents=[
            as_agent(plan, name="planner", reads="goal"),
            as_agent(work, name="worker", reads="sub:*"),
            as_agent(
                reduce,
                name="reducer",
                reads="res:*",
                trigger=lambda v: v.exists("sub:*")
                and v.count("res:*") == v.count("sub:*"),
            ),
        ]
    )
    store = Store()
    stream = ReactiveExecutor().stream(
        system,
        store,
        seed=[Fact(tag="goal", value="build report")],
        terminate=Goal(lambda v: v.exists("summary")),
    )
    async for r in stream:
        print(f"step {r.step}: {r.fired} -> {[f.tag for f in r.writes]}")
    print("summary:", store.snapshot().value("summary"))


if __name__ == "__main__":
    asyncio.run(main())
