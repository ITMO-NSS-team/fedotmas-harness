"""Reflection (P15): one agent revises its own work until it judges it done.

The same .loop as evaluator-optimizer, but the body is a single agent that folds the critic
into itself: it returns both the improved text and its own verdict on whether more work is
needed. The loop has no idea the critic is internal; the difference is entirely in the body.

Needs an OpenAI key in .env. Run: uv run --group examples python examples/sdk-llm/reflection.py
"""

import asyncio

from dotenv import load_dotenv
from pydantic import BaseModel

from fedotmas.adapters.pydantic_ai import PydanticAI
from fedotmas.engine.contract import Fact, View
from fedotmas.engine.executor import ReactiveExecutor
from fedotmas.engine.store import Store
from fedotmas.engine.terminate import Budget, Goal
from fedotmas.sdk import action

llm = PydanticAI("openai-responses:gpt-4o-mini")


class Revision(BaseModel):
    text: str
    good_enough: bool


@action
async def revise(state: dict, view: View) -> dict:
    r = await llm.complete(
        "Improve the sentence: stronger verbs, no filler. Set good_enough only when it needs no more edits.",
        state["text"],
        view,
        returns=Revision,
    )
    return {"text": r.text, "good_enough": r.good_enough}


async def main() -> None:
    load_dotenv()
    reflect = revise.loop(lambda s: s["good_enough"])
    store = Store()
    stream = ReactiveExecutor().stream(
        reflect.system(entry="seed", out="final"),
        store,
        seed=[
            Fact(
                tag="seed",
                value={
                    "text": "The thing was very very good and people liked it a lot.",
                    "good_enough": False,
                },
            )
        ],
        terminate=Goal(lambda v: v.exists("final")) | Budget(max_steps=8),
    )
    async for r in stream:
        print(f"step {r.step}: {r.fired} -> {[f.tag for f in r.writes]}")
    print("final:", store.snapshot().value("final")["text"])


if __name__ == "__main__":
    asyncio.run(main())
