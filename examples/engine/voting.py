import asyncio
from collections import Counter
from collections.abc import Awaitable, Callable

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

BALLOTS = {"s1": "A", "s2": "A", "s3": "B", "s4": "A", "s5": "B"}


def solver(name: str, answer: str) -> Callable[[object, View], Awaitable[Result]]:
    async def run(input: object, view: View) -> Result:
        return Result(writes=[Fact(tag=f"vote:{name}", value=answer)])

    return run


async def aggregate(input: object, view: View) -> Result:
    votes = [v.value for v in view.query("vote:*")]
    winner = Counter(votes).most_common(1)[0][0]
    return Result(writes=[Fact(tag="answer", value=winner)])


async def main() -> None:
    system = System(
        nodes=[
            *(
                as_node(solver(n, a), name=n, reads="question")
                for n, a in BALLOTS.items()
            ),
            as_node(
                aggregate,
                name="aggregator",
                reads="vote:*",
                trigger=lambda v: v.count("vote:*") == len(BALLOTS),
            ),
        ]
    )
    store = Store()
    stream = ReactiveExecutor().stream(
        system,
        store,
        seed=[Fact(tag="question", value="A or B?")],
        terminate=Goal(lambda v: v.exists("answer")),
    )
    async for r in stream:
        print(f"step {r.step}: {r.fired} -> {[f.tag for f in r.writes]}")
    print("answer:", store.snapshot().value("answer"))


if __name__ == "__main__":
    asyncio.run(main())
