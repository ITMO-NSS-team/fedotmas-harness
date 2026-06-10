"""Sectioning (P2): fork the same input into independent facets, join the reviews.

gather_all fans one text to three reviewers, each scoring a different facet, then a synthesizer
folds the list into one verdict. The list[str] output makes the join mandatory by type: the
fan-out is not a usable value until a reducer consumes it.

Needs an OpenAI key in .env. Run: uv run --group examples python examples/sdk-llm/sectioning.py
"""

import asyncio

from dotenv import load_dotenv

from fedotmas.adapters.pydantic_ai import PydanticAI
from fedotmas.engine.contract import Fact
from fedotmas.engine.executor import ReactiveExecutor
from fedotmas.engine.store import Store
from fedotmas.engine.terminate import Goal
from fedotmas.sdk import agent, gather_all

llm = PydanticAI("openai-responses:gpt-4o-mini")

clarity = agent(
    "clarity", prompt="Review only the clarity of this text in one sentence.", llm=llm
)
correctness = agent(
    "correctness",
    prompt="Review only the factual correctness in one sentence.",
    llm=llm,
)
tone = agent("tone", prompt="Review only the tone in one sentence.", llm=llm)
synthesize = agent(
    "synthesize",
    prompt="Combine these facet reviews into one short overall verdict.",
    takes=list,
    returns=str,
    llm=llm,
)

TEXT = (
    "Our app is basically the best thing ever and it literally never crashes, trust me."
)


async def main() -> None:
    load_dotenv()
    review = gather_all(clarity, correctness, tone) + synthesize
    store = Store()
    stream = ReactiveExecutor().stream(
        review.system(entry="text", out="verdict"),
        store,
        seed=[Fact(tag="text", value=TEXT)],
        terminate=Goal(lambda v: v.exists("verdict")),
    )
    async for r in stream:
        print(f"step {r.step}: {r.fired} -> {[f.tag for f in r.writes]}")
    print("verdict:", store.snapshot().value("verdict"))


if __name__ == "__main__":
    asyncio.run(main())
