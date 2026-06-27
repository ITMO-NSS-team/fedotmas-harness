import asyncio
from collections.abc import Awaitable, Callable

from fedotmas.engine import (
    Budget,
    Fact,
    Goal,
    ReactiveExecutor,
    Result,
    Store,
    System,
    View,
    as_node,
)

SPEAKERS = ["alice", "bob", "carol"]


async def manage(input: object, view: View) -> Result:
    n = view.count("turn:*")
    return Result(writes=[Fact(tag=f"turn:{n + 1}", value=SPEAKERS[n % len(SPEAKERS)])])


def speaker(name: str) -> Callable[[object, View], Awaitable[Result]]:
    async def run(input: object, view: View) -> Result:
        n = view.count("msg:*") + 1
        return Result(writes=[Fact(tag=f"msg:{n}", value=f"{name}: point {n}")])

    return run


def my_turn(name: str) -> Callable[[View], bool]:
    def check(v: View) -> bool:
        turns = v.query("turn:*")
        return bool(turns) and turns[-1].value == name and v.count("msg:*") < len(turns)

    return check


async def main() -> None:
    system = System(
        nodes=[
            as_node(
                manage,
                name="manager",
                reads="msg:*",
                trigger=lambda v: v.count("turn:*") == v.count("msg:*"),
            ),
            *(
                as_node(speaker(n), name=n, reads="turn:*", trigger=my_turn(n))
                for n in SPEAKERS
            ),
        ]
    )
    store = Store()
    stream = ReactiveExecutor().stream(
        system,
        store,
        seed=[Fact(tag="topic", value="ship it?")],
        terminate=Goal(lambda v: v.count("msg:*") >= 4) | Budget(max_steps=12),
    )
    async for r in stream:
        print(f"step {r.step}: {r.fired} -> {[f.tag for f in r.writes]}")
    print("transcript:", [f.value for f in store.snapshot().query("msg:*")])


if __name__ == "__main__":
    asyncio.run(main())
