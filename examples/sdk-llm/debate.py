"""Debate (P16): parallel pro and con each round, judged, looped until rounds run out.

A parallel product inside a .loop. Each round runs pro and con together on the threaded state;
the join is a judge that reads both arguments, scores the round, appends to the transcript, and
decrements the counter. The loop stops when the rounds are spent. pro and con each return the
full state so the judge can merge, since the product carries only its two branch outputs.

Needs an OpenAI key in .env. Run: uv run --group examples python examples/sdk-llm/debate.py
"""

import asyncio

from dotenv import load_dotenv

from fedotmas.adapters.pydantic_ai import PydanticAI
from fedotmas.engine.contract import Fact, View
from fedotmas.engine.executor import ReactiveExecutor
from fedotmas.engine.store import Store
from fedotmas.engine.terminate import Budget, Goal
from fedotmas.sdk import action

llm = PydanticAI("openai-responses:gpt-4o-mini")


def _ctx(s: dict) -> str:
    return f"Motion: {s['motion']}\nSo far: {s['transcript']}"


@action
async def pro(s: dict, view: View) -> dict:
    arg = await llm.complete(
        "Argue FOR the motion in one sharp sentence.", _ctx(s), view
    )
    return {**s, "pro": arg}


@action
async def con(s: dict, view: View) -> dict:
    arg = await llm.complete(
        "Argue AGAINST the motion in one sharp sentence.", _ctx(s), view
    )
    return {**s, "con": arg}


@action
async def judge(parts: tuple[dict, dict], view: View) -> dict:
    a, b = parts
    pro_arg, con_arg = a["pro"], b["con"]
    verdict = await llm.complete(
        "Who won this round? Reply with just 'pro' or 'con'.",
        f"PRO: {pro_arg}\nCON: {con_arg}",
        view,
    )
    transcript = [
        *a["transcript"],
        {"pro": pro_arg, "con": con_arg, "verdict": verdict},
    ]
    return {
        "motion": a["motion"],
        "transcript": transcript,
        "rounds_left": a["rounds_left"] - 1,
    }


async def main() -> None:
    load_dotenv()
    debate = ((pro * con) + judge).loop(lambda s: s["rounds_left"] <= 0)
    store = Store()
    stream = ReactiveExecutor().stream(
        debate.system(entry="seed", out="final"),
        store,
        seed=[
            Fact(
                tag="seed",
                value={
                    "motion": "small teams should build on a framework, not from scratch",
                    "transcript": [],
                    "rounds_left": 2,
                },
            )
        ],
        terminate=Goal(lambda v: v.exists("final")) | Budget(max_steps=20),
    )
    async for r in stream:
        print(f"step {r.step}: {r.fired} -> {[f.tag for f in r.writes]}")
    for round in store.snapshot().value("final")["transcript"]:
        print(
            f"  round to {round['verdict']}: pro={round['pro']!r} con={round['con']!r}"
        )


if __name__ == "__main__":
    asyncio.run(main())
