"""blackboard: agents self-activate on author-written conditions, no edges.

Same shape as the hand-written engine/blackboard.py. These three are a linear chain, so they
lean on the produce-once default (fire when `reads` is present and `writes` is not yet) and
need no explicit trigger. The arrows still cannot express the surface in general: activation is
opportunistic, write `when` once a rule depends on more than one read. See sdk-llm/blackboard.py
for a genuinely non-linear case.
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
        Rule("hypothesizer", hypothesize, writes="hypothesis", reads="question"),
        Rule("researcher", research, writes="evidence", reads="hypothesis"),
        Rule("verifier", verify, writes="conclusion", reads="evidence"),
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
