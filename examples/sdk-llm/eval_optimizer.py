"""Evaluator-Optimizer (P6): generate then critique, looped until the critic approves.

A two-stage body, (generate + critique), threaded through .loop. State is a dict carrying the
draft and the critic's verdict; the loop feeds each round's state into the next. The critic
returns a typed verdict (approved + feedback), so the stop condition reads a real boolean, not
a parsed string. Budget caps the loop if the critic is never satisfied.

Needs an OpenAI key in .env. Run: uv run --group examples python examples/sdk-llm/eval_optimizer.py
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


class Verdict(BaseModel):
    approved: bool
    feedback: str


@action
async def generate(state: dict, view: View) -> dict:
    fb = state.get("feedback") or "none yet"
    prompt = f"Write a haiku about {state['task']}. Address this feedback: {fb}"
    draft = await llm.complete(
        "You are a careful poet who writes 5-7-5 haiku.", prompt, view
    )
    return {**state, "draft": draft}


@action
async def critique(state: dict, view: View) -> dict:
    v = await llm.complete(
        "Judge the haiku. Approve only if it is genuinely 5-7-5 and evocative.",
        state["draft"],
        view,
        returns=Verdict,
    )
    return {**state, "approved": v.approved, "feedback": v.feedback}


async def main() -> None:
    load_dotenv()
    optimize = (generate + critique).loop(lambda s: s["approved"])
    store = Store()
    stream = ReactiveExecutor().stream(
        optimize.system(entry="seed", out="final"),
        store,
        seed=[
            Fact(
                tag="seed",
                value={
                    "task": "first snow on a quiet harbor",
                    "approved": False,
                    "feedback": "",
                },
            )
        ],
        terminate=Goal(lambda v: v.exists("final")) | Budget(max_steps=12),
    )
    async for r in stream:
        print(f"step {r.step}: {r.fired} -> {[f.tag for f in r.writes]}")
    final = store.snapshot().value("final")
    print("approved:", final["approved"])
    print("haiku:", final["draft"])


if __name__ == "__main__":
    asyncio.run(main())
