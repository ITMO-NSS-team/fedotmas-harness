"""DAG (P5): a diamond. extract -> (support * oppose) -> balance.

One claim fans into two opposed researchers that run together, then a join weighs both. The
parallel product types as tuple[str, str], so balance must consume the pair: forget the join
and the + is a type error, not a lost branch at runtime.

Needs an OpenAI key in .env. Run: uv run --group examples python examples/sdk-llm/dag.py
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

extract = agent(
    "extract",
    prompt="State the single central claim of this text in one sentence.",
    llm=llm,
)
support = agent(
    "support",
    prompt="Give the strongest one-sentence argument FOR this claim.",
    llm=llm,
)
oppose = agent(
    "oppose",
    prompt="Give the strongest one-sentence argument AGAINST this claim.",
    llm=llm,
)
balance = agent(
    "balance",
    prompt="Given a (for, against) pair, write one balanced verdict sentence.",
    takes=tuple,
    returns=str,
    llm=llm,
)

TEXT = "Remote work makes teams more productive than any office ever could."


async def main() -> None:
    load_dotenv()
    diamond = extract + (support * oppose) + balance
    store = Store()
    stream = ReactiveExecutor().stream(
        diamond.system(entry="text", out="verdict"),
        store,
        seed=[Fact(tag="text", value=TEXT)],
        terminate=Goal(lambda v: v.exists("verdict")),
    )
    async for r in stream:
        print(f"step {r.step}: {r.fired} -> {[f.tag for f in r.writes]}")
    print("verdict:", store.snapshot().value("verdict"))


if __name__ == "__main__":
    asyncio.run(main())
