"""Mixture-of-Agents (P7): layered parallel with aggregation between layers."""

import asyncio
from collections.abc import Awaitable, Callable

from fedotmas.engine import as_node
from fedotmas.engine.contract import Fact, Result, View
from fedotmas.engine.executor import ReactiveExecutor
from fedotmas.engine.store import Store
from fedotmas.engine.system import System
from fedotmas.engine.terminate import Goal

WIDTH = 3


def proposer(layer: str, idx: int) -> Callable[[object, View], Awaitable[Result]]:
    async def run(input: object, view: View) -> Result:
        return Result(writes=[Fact(tag=f"{layer}:{idx}", value=f"{layer}#{idx}")])

    return run


def synth(layer: str, out: str) -> Callable[[object, View], Awaitable[Result]]:
    async def run(input: object, view: View) -> Result:
        parts = [p.value for p in view.query(f"{layer}:*")]
        return Result(writes=[Fact(tag=out, value=" + ".join(parts))])

    return run


async def main() -> None:
    system = System(
        nodes=[
            *(
                as_node(proposer("l1", i), name=f"a{i}", reads="q")
                for i in range(WIDTH)
            ),
            as_node(
                synth("l1", "mix1"),
                name="synth1",
                reads="l1:*",
                trigger=lambda v: v.count("l1:*") == WIDTH,
            ),
            *(
                as_node(proposer("l2", i), name=f"b{i}", reads="mix1")
                for i in range(WIDTH)
            ),
            as_node(
                synth("l2", "answer"),
                name="synth2",
                reads="l2:*",
                trigger=lambda v: v.count("l2:*") == WIDTH,
            ),
        ]
    )
    store = Store()
    stream = ReactiveExecutor().stream(
        system,
        store,
        seed=[Fact(tag="q", value="prompt")],
        terminate=Goal(lambda v: v.exists("answer")),
    )
    async for r in stream:
        print(f"step {r.step}: {r.fired} -> {[f.tag for f in r.writes]}")
    print("answer:", store.snapshot().value("answer"))


if __name__ == "__main__":
    asyncio.run(main())
