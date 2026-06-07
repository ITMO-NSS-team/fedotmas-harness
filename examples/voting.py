"""Voting (P3 Self-Consistency, P4 Ensemble): replicate -> join(vote).

Self-Consistency = one model sampled N times; Ensemble = N distinct models.
On the engine they are identical: parallel fan-out into a majority aggregator.
"""

import asyncio
from collections import Counter
from collections.abc import Awaitable, Callable

from fedotmas.adapters import as_agent
from fedotmas.engine.contract import Fact, Result, View
from fedotmas.engine.executor import ReactiveExecutor
from fedotmas.engine.store import Store
from fedotmas.engine.system import System
from fedotmas.engine.terminate import Goal

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
        agents=[
            *(
                as_agent(solver(n, a), name=n, reads="question")
                for n, a in BALLOTS.items()
            ),
            as_agent(
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
