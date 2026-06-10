"""A blackboard enters the arrow world as one embedded node.

The rule surface (opportunistic, non-linear, uncheckable interior) is wrapped by embed
into a Flow[str, str] with a typed boundary, then composed between two ordinary actions.
The blackboard runs in its own inner store to its goal; outside it is one opaque arrow.
"""

import asyncio

from fedotmas.sdk import Flow, Rule, action, blackboard, embed
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


investigation = blackboard(
    Rule("hypothesizer", hypothesize, writes="hypothesis", reads="question"),
    Rule("researcher", research, writes="evidence", reads="hypothesis"),
    Rule("verifier", verify, writes="conclusion", reads="evidence"),
)

solve: Flow[str, str] = embed(investigation, entry="question", out="conclusion")


@action
async def frame(topic: str, view: View) -> str:
    return f"what is {topic}?"


@action
async def report(conclusion: str, view: View) -> str:
    return f"REPORT: {conclusion}"


async def main() -> None:
    pipeline = frame + solve + report
    store = Store()
    stream = ReactiveExecutor().stream(
        pipeline.system(entry="topic", out="out"),
        store,
        seed=[Fact(tag="topic", value="the artifact")],
        terminate=Goal(lambda v: v.exists("out")),
    )
    async for r in stream:
        print(f"step {r.step}: {r.fired} -> {[f.tag for f in r.writes]}")
    print("out:", store.snapshot().value("out"))


if __name__ == "__main__":
    asyncio.run(main())
