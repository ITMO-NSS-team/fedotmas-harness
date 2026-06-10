"""Prompt Chaining (P1) on the SDK: a + b + c, each LLM node feeding the next.

The flat sequence the arrow algebra was built for. Three prompts lifted to agents and stitched
with +; the type str -> str -> str -> str checks the chain before any model runs. No model is
named in the composition, only in the binding.

Needs an OpenAI key in .env. Run: uv run --group examples python examples/sdk-llm/prompt_chaining.py
"""

import asyncio

from dotenv import load_dotenv

from fedotmas.adapters.pydantic_ai import PydanticAI
from fedotmas.engine.contract import Fact
from fedotmas.engine.executor import ReactiveExecutor
from fedotmas.engine.store import Store
from fedotmas.engine.terminate import Goal
from fedotmas.sdk import agent

llm = PydanticAI("openai-responses:gpt-4o-mini")

outline = agent(
    "outline",
    prompt="Give a tight 3-bullet outline for a short article on the topic.",
    llm=llm,
)
draft = agent(
    "draft", prompt="Write a single vivid paragraph from this outline.", llm=llm
)
polish = agent(
    "polish", prompt="Cut this paragraph down to two crisp sentences.", llm=llm
)


async def main() -> None:
    load_dotenv()
    chain = outline + draft + polish
    store = Store()
    stream = ReactiveExecutor().stream(
        chain.system(entry="topic", out="article"),
        store,
        seed=[Fact(tag="topic", value="why a blackboard suits multi-agent systems")],
        terminate=Goal(lambda v: v.exists("article")),
    )
    async for r in stream:
        print(f"step {r.step}: {r.fired} -> {[f.tag for f in r.writes]}")
    print("article:", store.snapshot().value("article"))


if __name__ == "__main__":
    asyncio.run(main())
