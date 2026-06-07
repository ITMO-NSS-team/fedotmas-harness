"""Router (P8): classifier writes a label, exactly one target activates."""

import asyncio
from collections.abc import Awaitable, Callable

from fedotmas.adapters import as_agent
from fedotmas.engine.contract import Fact, Result, View
from fedotmas.engine.executor import ReactiveExecutor
from fedotmas.engine.store import Store
from fedotmas.engine.system import System
from fedotmas.engine.terminate import Goal


async def classify(input: object, view: View) -> Result:
    return Result(writes=[Fact(tag="route", value="math")])


def handler(label: str) -> Callable[[object, View], Awaitable[Result]]:
    async def run(input: object, view: View) -> Result:
        return Result(writes=[Fact(tag="answer", value=f"{label} handled")])

    return run


def routed(label: str) -> Callable[[View], bool]:
    return lambda v: v.value("route") == label


async def main() -> None:
    system = System(
        agents=[
            as_agent(classify, name="classifier", reads="q"),
            as_agent(
                handler("code"), name="coder", reads="route", trigger=routed("code")
            ),
            as_agent(
                handler("prose"), name="writer", reads="route", trigger=routed("prose")
            ),
            as_agent(
                handler("math"), name="solver", reads="route", trigger=routed("math")
            ),
        ]
    )
    store = Store()
    stream = ReactiveExecutor().stream(
        system,
        store,
        seed=[Fact(tag="q", value="2 + 2")],
        terminate=Goal(lambda v: v.exists("answer")),
    )
    async for r in stream:
        print(f"step {r.step}: {r.fired} -> {[f.tag for f in r.writes]}")
    print("answer:", store.snapshot().value("answer"))


if __name__ == "__main__":
    asyncio.run(main())
