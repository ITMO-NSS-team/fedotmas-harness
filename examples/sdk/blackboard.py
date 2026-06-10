"""blackboard: rules self-activate on author-written conditions, no edges.

Same shape as the hand-written engine/blackboard.py. A rule is a self-activating node; these
three are a linear chain, so they lean on the produce-once default (fire when `reads` is
present and `writes` is not yet) and need no explicit trigger. The arrows still cannot express
the surface in general: activation is opportunistic, write `when` once a rule depends on more
than one read. See sdk-llm/blackboard.py for a genuinely non-linear case. blackboard() returns
a Board; board.run derives the store and the terminate condition from the seed and the goal.
"""

import asyncio

from fedotmas.engine.contract import View
from fedotmas.sdk import blackboard, rule


async def hypothesize(input: object, view: View) -> str:
    return "it is X"


async def research(input: object, view: View) -> str:
    return "supports X"


async def verify(input: object, view: View) -> str:
    return "X confirmed"


async def main() -> None:
    board = blackboard(
        rule("hypothesizer", hypothesize, writes="hypothesis", reads="question"),
        rule("researcher", research, writes="evidence", reads="hypothesis"),
        rule("verifier", verify, writes="conclusion", reads="evidence"),
    )
    run = await board.run({"question": "what is it?"}, goal="conclusion")
    for r in run.steps:
        print(f"step {r.step}: {r.fired} -> {[f.tag for f in r.writes]}")
    assert run.ok and run.value == "X confirmed", (run.reason, run.value)
    print("conclusion:", run.value)


if __name__ == "__main__":
    asyncio.run(main())
