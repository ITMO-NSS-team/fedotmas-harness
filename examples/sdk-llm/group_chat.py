"""Group Chat (P11): a manager picks the next speaker, the speaker adds to the transcript.

A decision-driven branch inside a .loop. Each round the manager (an LLM router over the
speaker names) chooses who talks next, the chosen role appends one line to the threaded
transcript, and the loop runs until the transcript is long enough. The next speaker is an LLM
choice, not a fixed rotation, which is what separates this from a plain round-robin.

Needs an OpenAI key in .env. Run: uv run --group examples python examples/sdk-llm/group_chat.py
"""

import asyncio

from dotenv import load_dotenv

from fedotmas.adapters.pydantic_ai import PydanticAI
from fedotmas.engine.contract import Fact, View
from fedotmas.engine.executor import ReactiveExecutor
from fedotmas.engine.store import Store
from fedotmas.engine.terminate import Budget, Goal
from fedotmas.sdk import Flow, action, branch, decision

llm = PydanticAI("openai-responses:gpt-4o-mini")

SPEAKERS = ["pm", "engineer", "designer"]

manager = decision(
    "manager",
    prompt="Given the running transcript, pick who speaks next. Reply with exactly one word and nothing else: pm, engineer, or designer.",
    labels=SPEAKERS,
    takes=dict,
    llm=llm,
)


def speaker(name: str) -> Flow[dict, dict]:
    async def contribute(s: dict, view: View) -> dict:
        reply = await llm.complete(
            f"You are the {name}. Add one short point to the discussion.",
            str(s["transcript"]),
            view,
        )
        return {**s, "transcript": [*s["transcript"], f"{name}: {reply}"]}

    contribute.__name__ = name
    return action(contribute)


async def main() -> None:
    load_dotenv()
    chat_round = branch(manager, {n: speaker(n) for n in SPEAKERS})
    group_chat = chat_round.loop(lambda s: len(s["transcript"]) >= 4)
    store = Store()
    stream = ReactiveExecutor().stream(
        group_chat.system(entry="seed", out="final"),
        store,
        seed=[
            Fact(
                tag="seed",
                value={
                    "topic": "should we ship the beta this week?",
                    "transcript": ["topic: should we ship the beta this week?"],
                },
            )
        ],
        terminate=Goal(lambda v: v.exists("final")) | Budget(max_steps=16),
    )
    async for r in stream:
        print(f"step {r.step}: {r.fired} -> {[f.tag for f in r.writes]}")
    for line in store.snapshot().value("final")["transcript"]:
        print(" ", line)


if __name__ == "__main__":
    asyncio.run(main())
