import asyncio

from fedotmas.engine import (
    Fact,
    Goal,
    ReactiveExecutor,
    Result,
    Store,
    System,
    View,
    as_node,
)

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
        nodes=[
            as_node(plan, name="planner", reads="goal"),
            as_node(work, name="worker", reads="sub:*"),
            as_node(
                reduce,
                name="reducer",
                reads="res:*",
                trigger=lambda v: (
                    v.exists("sub:*") and v.count("res:*") == v.count("sub:*")
                ),
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
