"""Voting (P3 Self-Consistency, P4 Ensemble): gather_all replicas, fold by majority.

Three decisions classify the same review against one finite label set, and a mechanical
majority reduces the list to one label. Self-consistency samples one prompt N times; ensemble
uses N distinct graders. On the arrow they are the same shape: gather_all + a reducer. The reducer
is an action, not an agent, because counting votes needs no model.

Needs an OpenAI key in .env. Run: uv run --group examples python examples/sdk-llm/voting.py
"""

import asyncio
from collections import Counter

from dotenv import load_dotenv

from fedotmas.adapters.pydantic_ai import PydanticAI
from fedotmas.engine.contract import Fact, View
from fedotmas.engine.executor import ReactiveExecutor
from fedotmas.engine.store import Store
from fedotmas.engine.terminate import Goal
from fedotmas.sdk import Flow, action, decision, gather_all

llm = PydanticAI("openai-responses:gpt-4o-mini")

LABELS = ["positive", "negative", "neutral"]


def grader(name: str, lens: str) -> Flow[str, str]:
    return decision(
        name,
        prompt=f"As a {lens}, classify the review sentiment. Reply with exactly one word and nothing else: positive, negative, or neutral.",
        labels=LABELS,
        llm=llm,
    )


@action
async def majority(votes: list[str], view: View) -> str:
    return Counter(votes).most_common(1)[0][0]


REVIEW = "The interface is gorgeous, but it crashed twice and lost my work."


async def main() -> None:
    load_dotenv()
    panel = gather_all(
        grader("strict_critic", "strict critic"),
        grader("casual_user", "casual user"),
        grader("support_agent", "support agent"),
    )
    vote = panel + majority
    store = Store()
    stream = ReactiveExecutor().stream(
        vote.system(entry="review", out="sentiment"),
        store,
        seed=[Fact(tag="review", value=REVIEW)],
        terminate=Goal(lambda v: v.exists("sentiment")),
    )
    async for r in stream:
        print(f"step {r.step}: {r.fired} -> {[f.tag for f in r.writes]}")
    print("sentiment:", store.snapshot().value("sentiment"))


if __name__ == "__main__":
    asyncio.run(main())
