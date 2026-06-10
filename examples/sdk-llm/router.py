"""Router (P8): a decision picks one case by a label, exactly one specialist runs.

branch takes a decision (an LLM router over a finite label set) and a dict of cases. The
decision writes the label, the router feeds the original request only to the chosen case, and
the other cases never wake. Every case is a Flow[str, str], so they are interchangeable by type.

Needs an OpenAI key in .env. Run: uv run --group examples python examples/sdk-llm/router.py
"""

import asyncio

from dotenv import load_dotenv

from fedotmas.adapters.pydantic_ai import PydanticAI
from fedotmas.engine.contract import Fact
from fedotmas.engine.executor import ReactiveExecutor
from fedotmas.engine.store import Store
from fedotmas.engine.terminate import Goal
from fedotmas.sdk import agent, branch, decision

llm = PydanticAI("openai-responses:gpt-4o-mini")

route = decision(
    "route",
    prompt="Classify the request. Reply with exactly one word and nothing else: math, prose, or code.",
    labels=["math", "prose", "code"],
    llm=llm,
)
solver = agent(
    "solver",
    prompt="Solve the math problem, give the number and one line of reasoning.",
    llm=llm,
)
writer = agent(
    "writer", prompt="Answer the request in a short prose paragraph.", llm=llm
)
coder = agent(
    "coder", prompt="Answer the request with a small Python snippet.", llm=llm
)


async def run(q: str) -> None:
    router = branch(route, {"math": solver, "prose": writer, "code": coder})
    store = Store()
    stream = ReactiveExecutor().stream(
        router.system(entry="request", out="answer"),
        store,
        seed=[Fact(tag="request", value=q)],
        terminate=Goal(lambda v: v.exists("answer")),
    )
    print(f"request: {q!r}")
    async for r in stream:
        print(f"  step {r.step}: {r.fired} -> {[f.tag for f in r.writes]}")
    print("  answer:", store.snapshot().value("answer"))


async def main() -> None:
    load_dotenv()
    await run("what is 17 * 23?")
    await run("write a haiku about the sea")


if __name__ == "__main__":
    asyncio.run(main())
