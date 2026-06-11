"""blackboard: rules self-activate on author-written conditions, no edges.

Same shape as the hand-written engine/blackboard.py. A rule is a self-activating node; the
first three lean on the produce-once default (fire when `reads` is present and `writes` is not
yet) and need no explicit trigger. researcher and skeptic wake on the same hypothesis and fire
in one parallel step; verifier waits on both their facts at once, a condition not reducible to
one read, so it spells out `when` as a tag list (`!` marks a fact that must be absent). That
opportunistic activation is what the arrows cannot express. blackboard() returns a Board;
board.run derives the store and the terminate condition from the seed and the goal.
"""

import asyncio

from fedotmas.engine.contract import View
from fedotmas.sdk import Rule, blackboard


async def hypothesize(input: object, view: View) -> str:
    return "it is X"


async def research(input: object, view: View) -> str:
    return "supports X"


async def object_(input: object, view: View) -> str:
    return "unless it is Y"


async def verify(input: object, view: View) -> str:
    return "X confirmed"


async def main() -> None:
    board = blackboard(
        Rule("hypothesizer", hypothesize, writes="hypothesis", reads="question"),
        Rule("researcher", research, writes="evidence", reads="hypothesis"),
        Rule("skeptic", object_, writes="objection", reads="hypothesis"),
        Rule(
            "verifier",
            verify,
            writes="conclusion",
            reads="evidence",
            when=["evidence", "objection", "!conclusion"],
        ),
    )
    run = await board.run({"question": "what is it?"}, goal="conclusion")
    for r in run.steps:
        print(f"step {r.step}: {r.fired} -> {[f.tag for f in r.writes]}")
    assert run.ok and run.value == "X confirmed", (run.reason, run.value)
    assert any(len(r.fired) == 2 for r in run.steps), "researcher+skeptic fire together"
    print("conclusion:", run.value)


if __name__ == "__main__":
    asyncio.run(main())
