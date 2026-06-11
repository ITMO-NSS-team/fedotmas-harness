"""Blackboard (P13): no edges, agents self-activate on author-written conditions."""

import asyncio

from fedotmas.engine import as_node
from fedotmas.engine.contract import Fact, Result, View
from fedotmas.engine.executor import ReactiveExecutor
from fedotmas.engine.store import Store
from fedotmas.engine.system import System
from fedotmas.engine.terminate import Goal


async def hypothesize(input: object, view: View) -> Result:
    return Result(writes=[Fact(tag="hypothesis", value="it is X")])


async def research(input: object, view: View) -> Result:
    return Result(writes=[Fact(tag="evidence", value="supports X")])


async def verify(input: object, view: View) -> Result:
    return Result(writes=[Fact(tag="conclusion", value="X confirmed")])


async def main() -> None:
    system = System(
        nodes=[
            as_node(
                hypothesize,
                name="hypothesizer",
                reads="question",
                trigger=lambda v: v.exists("question") and not v.exists("hypothesis"),
            ),
            as_node(
                research,
                name="researcher",
                reads="hypothesis",
                trigger=lambda v: v.exists("hypothesis") and not v.exists("evidence"),
            ),
            as_node(
                verify,
                name="verifier",
                reads="evidence",
                trigger=lambda v: v.exists("evidence") and not v.exists("conclusion"),
            ),
        ]
    )
    store = Store()
    stream = ReactiveExecutor().stream(
        system,
        store,
        seed=[Fact(tag="question", value="what is it?")],
        terminate=Goal(lambda v: v.exists("conclusion")),
    )
    async for r in stream:
        print(f"step {r.step}: {r.fired} -> {[f.tag for f in r.writes]}")
    print("conclusion:", store.snapshot().value("conclusion"))


if __name__ == "__main__":
    asyncio.run(main())
