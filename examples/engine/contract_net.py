"""Contract-Net (P14): bidders contend for a task, an auction Policy awards the winner."""

import asyncio
from collections.abc import Awaitable, Callable

from fedotmas.adapters import as_node
from fedotmas.engine.contract import Fact, Result, View
from fedotmas.engine.executor import ReactiveExecutor
from fedotmas.engine.policy import AuctionSelect
from fedotmas.engine.store import Store
from fedotmas.engine.system import System
from fedotmas.engine.terminate import Goal

BIDS = {"w1": 0.3, "w2": 0.9, "w3": 0.5}


def worker(name: str) -> Callable[[object, View], Awaitable[Result]]:
    async def run(input: object, view: View) -> Result:
        return Result(
            writes=[
                Fact(tag="award", value=name),
                Fact(tag="result", value=f"{name} executed the task"),
            ]
        )

    return run


def open_task(v: View) -> bool:
    return v.exists("task") and not v.exists("award")


async def main() -> None:
    system = System(
        nodes=[
            as_node(worker(n), name=n, reads="task", trigger=open_task) for n in BIDS
        ]
    )
    store = Store()
    stream = ReactiveExecutor().stream(
        system,
        store,
        seed=[Fact(tag="task", value="haul cargo")],
        terminate=Goal(lambda v: v.exists("result")),
        policy=AuctionSelect(key=lambda a, v: BIDS[a.name]),
    )
    async for r in stream:
        print(f"step {r.step}: {r.fired} -> {[f.tag for f in r.writes]}")
    snap = store.snapshot()
    print("award:", snap.value("award"), "| result:", snap.value("result"))


if __name__ == "__main__":
    asyncio.run(main())
