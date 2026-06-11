"""Sectioning (P2): fork-join. splitter -> {a, b, c} -> join(concat)."""

import asyncio
from collections.abc import Awaitable, Callable

from fedotmas.engine import as_node
from fedotmas.engine.contract import Fact, Result, View
from fedotmas.engine.executor import ReactiveExecutor
from fedotmas.engine.store import Store
from fedotmas.engine.system import System
from fedotmas.engine.terminate import Goal

PARTS = ["a", "b", "c"]


async def split(input: object, view: View) -> Result:
    return Result(writes=[Fact(tag=f"part:{p}", value=p.upper()) for p in PARTS])


def worker(part: str) -> Callable[[object, View], Awaitable[Result]]:
    async def run(input: object, view: View) -> Result:
        return Result(
            writes=[Fact(tag=f"out:{part}", value=f"<{view.value(f'part:{part}')}>")]
        )

    return run


async def join(input: object, view: View) -> Result:
    pieces = view.query("out:*")
    return Result(writes=[Fact(tag="result", value="".join(p.value for p in pieces))])


async def main() -> None:
    system = System(
        nodes=[
            as_node(split, name="splitter", reads="task"),
            *(as_node(worker(p), name=p, reads=f"part:{p}") for p in PARTS),
            as_node(
                join,
                name="join",
                reads="out:*",
                trigger=lambda v: v.count("out:*") == 3,
            ),
        ]
    )
    store = Store()
    stream = ReactiveExecutor().stream(
        system,
        store,
        seed=[Fact(tag="task", value="split me")],
        terminate=Goal(lambda v: v.exists("result")),
    )
    async for r in stream:
        print(f"step {r.step}: {r.fired} -> {[f.tag for f in r.writes]}")
    print("result:", store.snapshot().value("result"))


if __name__ == "__main__":
    asyncio.run(main())
