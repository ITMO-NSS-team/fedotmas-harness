"""A blackboard enters the arrow world as one nested node.

The blackboard surface (opportunistic, non-linear, uncheckable interior) is wrapped by nest
into a Flow[str, str] with a typed boundary, then composed between two ordinary actions.
The board runs in its own inner store to its goal; outside it is one opaque arrow.
"""

import asyncio

from fedotmas.engine.contract import View
from fedotmas.sdk import Flow, Rule, action, blackboard, nest


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

solve: Flow[str, str] = nest(investigation, entry="question", out="conclusion")


@action
async def frame(topic: str, view: View) -> str:
    return f"what is {topic}?"


@action
async def report(conclusion: str, view: View) -> str:
    return f"REPORT: {conclusion}"


async def main() -> None:
    pipeline = frame + solve + report
    run = await pipeline.run("the artifact")
    for r in run.steps:
        print(f"step {r.step}: {r.fired} -> {[f.tag for f in r.writes]}")
    assert run.ok and run.value == "REPORT: X confirmed", (run.reason, run.value)
    print("out:", run.value)


if __name__ == "__main__":
    asyncio.run(main())
