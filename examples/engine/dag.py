"""DAG (P5): diamond dependency. a -> {b, c} -> d, where d waits on both b and c."""

import asyncio

from fedotmas.adapters import as_node
from fedotmas.engine.contract import Fact, Result, View
from fedotmas.engine.executor import ReactiveExecutor
from fedotmas.engine.store import Store
from fedotmas.engine.system import System
from fedotmas.engine.terminate import Goal


async def a(input: object, view: View) -> Result:
    return Result(writes=[Fact(tag="out:a", value=1)])


async def b(input: object, view: View) -> Result:
    return Result(writes=[Fact(tag="out:b", value=view.value("out:a") + 1)])


async def c(input: object, view: View) -> Result:
    return Result(writes=[Fact(tag="out:c", value=view.value("out:a") + 10)])


async def d(input: object, view: View) -> Result:
    total = view.value("out:b") + view.value("out:c")
    return Result(writes=[Fact(tag="out:d", value=total)])


async def main() -> None:
    system = System(
        nodes=[
            as_node(a, name="a", reads="in"),
            as_node(b, name="b", reads="out:a"),
            as_node(c, name="c", reads="out:a"),
            as_node(
                d,
                name="d",
                reads="out:*",
                trigger=lambda v: v.exists("out:b") and v.exists("out:c"),
            ),
        ]
    )
    store = Store()
    stream = ReactiveExecutor().stream(
        system,
        store,
        seed=[Fact(tag="in", value=0)],
        terminate=Goal(lambda v: v.exists("out:d")),
    )
    async for r in stream:
        print(f"step {r.step}: {r.fired} -> {[f.tag for f in r.writes]}")
    print("out:d:", store.snapshot().value("out:d"))


if __name__ == "__main__":
    asyncio.run(main())
