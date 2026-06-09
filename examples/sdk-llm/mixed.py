"""A mixed pipeline: two LLM nodes around a deterministic python node.

The LLM extracts structure from prose and phrases the answer; the exact arithmetic runs in
plain python, the one thing an LLM should not be trusted with. extract returns a typed
Problem via pydantic-ai structured output, so the boundary is typed all the way to the
model: str -> Problem -> float -> str, each stitch checked by ty. LLM is one kind of atom,
not a requirement; the mechanical node composes identically.

Needs an OpenAI key in .env. Run: uv run --group examples python examples/sdk-llm/mixed.py
"""

import asyncio
from typing import Literal

from dotenv import load_dotenv
from pydantic import BaseModel

from fedotmas.adapters.pydantic_ai import PydanticAI
from fedotmas.engine.contract import Fact, View
from fedotmas.engine.executor import ReactiveExecutor
from fedotmas.engine.store import Store
from fedotmas.engine.terminate import Goal
from fedotmas.sdk import action, agent


class Problem(BaseModel):
    a: float
    b: float
    op: Literal["+", "-", "*", "/"]


llm = PydanticAI("openai-responses:gpt-4o-mini")

extract = agent(
    "extract",
    prompt="Extract the two operands and the arithmetic operator from the problem.",
    takes=str,
    returns=Problem,
    llm=llm,
)

phrase = agent(
    "phrase",
    prompt="State the numeric result in one friendly sentence.",
    takes=float,
    returns=str,
    llm=llm,
)


@action
async def compute(p: Problem, view: View) -> float:
    return {"+": p.a + p.b, "-": p.a - p.b, "*": p.a * p.b, "/": p.a / p.b}[p.op]


async def main() -> None:
    load_dotenv()
    pipeline = extract + compute + phrase
    store = Store()
    stream = ReactiveExecutor().stream(
        pipeline.system(entry="problem", out="out"),
        store,
        seed=[Fact(tag="problem", value="What is 1234 times 5678?")],
        terminate=Goal(lambda v: v.exists("out")),
    )
    async for r in stream:
        print(f"step {r.step}: {r.fired} -> {[f.tag for f in r.writes]}")
    print("out:", store.snapshot().value("out"))


if __name__ == "__main__":
    asyncio.run(main())
