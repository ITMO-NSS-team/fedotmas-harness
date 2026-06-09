"""blackboard: agents self-activate on author-written conditions, no edges.

Same shape as the hand-written engine/blackboard.py. Each Rule carries its own `when`
predicate, the helper owns the Result/Fact. The arrows cannot express this: there
is no fixed topology, activation is opportunistic.
"""

import asyncio

from fedotmas.sdk import Rule, blackboard
from fedotmas.engine.contract import Fact, View
from fedotmas.engine.executor import ReactiveExecutor
from fedotmas.engine.store import Store
from fedotmas.engine.terminate import Goal


async def hypothesize(input: object, view: View) -> str:
    return "it is X"


async def research(input: object, view: View) -> str:
    return "supports X"


async def verify(input: object, view: View) -> str:
    return "X confirmed"


async def main() -> None:
    system = blackboard(
        Rule(
            "hypothesizer",
            lambda v: v.exists("question") and not v.exists("hypothesis"),
            hypothesize,
            writes="hypothesis",
        ),
        Rule(
            "researcher",
            lambda v: v.exists("hypothesis") and not v.exists("evidence"),
            research,
            writes="evidence",
        ),
        Rule(
            "verifier",
            lambda v: v.exists("evidence") and not v.exists("conclusion"),
            verify,
            writes="conclusion",
        ),
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
