"""Debate (P16): loop of parallel pro/con rounds judged each round, transcript accrues."""

import asyncio

from fedotmas.adapters import as_agent
from fedotmas.engine.contract import Fact, Result, View
from fedotmas.engine.executor import ReactiveExecutor
from fedotmas.engine.store import Store
from fedotmas.engine.system import System
from fedotmas.engine.terminate import Goal

ROUNDS = 3


async def pro(input: object, view: View) -> Result:
    r = view.count("verdict:*") + 1
    return Result(writes=[Fact(tag=f"pro:{r}", value=f"pro argues {r}")])


async def con(input: object, view: View) -> Result:
    r = view.count("verdict:*") + 1
    return Result(writes=[Fact(tag=f"con:{r}", value=f"con argues {r}")])


async def judge(input: object, view: View) -> Result:
    r = view.count("verdict:*") + 1
    return Result(writes=[Fact(tag=f"verdict:{r}", value=f"round {r} to pro")])


def opened(v: View) -> bool:
    return v.count("pro:*") == v.count("verdict:*") and v.count("verdict:*") < ROUNDS


def both_spoke(v: View) -> bool:
    n = v.count("verdict:*")
    return v.count("pro:*") > n and v.count("con:*") > n


async def main() -> None:
    system = System(
        agents=[
            as_agent(pro, name="pro", reads="verdict:*", trigger=opened),
            as_agent(con, name="con", reads="verdict:*", trigger=opened),
            as_agent(judge, name="judge", reads="pro:*", trigger=both_spoke),
        ]
    )
    store = Store()
    stream = ReactiveExecutor().stream(
        system,
        store,
        seed=[Fact(tag="motion", value="AI is good")],
        terminate=Goal(lambda v: v.count("verdict:*") >= ROUNDS),
    )
    async for r in stream:
        print(f"step {r.step}: {r.fired} -> {[f.tag for f in r.writes]}")
    print("verdicts:", [f.value for f in store.snapshot().query("verdict:*")])


if __name__ == "__main__":
    asyncio.run(main())
