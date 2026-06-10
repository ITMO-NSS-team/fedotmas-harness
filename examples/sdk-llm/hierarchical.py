"""Hierarchical Teams (P12): a whole sub-flow embedded as one node in an outer flow.

A research team (two searchers fanned by gather_all, then a summarizer) is its own Flow. embed
wraps it as one typed arrow with its own inner store, so from the outer chain it is a single
opaque step. Nesting is free: the team composes into frame + team + report exactly like an atom.

Needs an OpenAI key in .env. Run: uv run --group examples python examples/sdk-llm/hierarchical.py
"""

import asyncio

from dotenv import load_dotenv

from fedotmas.adapters.pydantic_ai import PydanticAI
from fedotmas.engine.contract import Fact
from fedotmas.engine.executor import ReactiveExecutor
from fedotmas.engine.store import Store
from fedotmas.engine.terminate import Goal
from fedotmas.sdk import Flow, agent, embed, gather_all

llm = PydanticAI("openai-responses:gpt-4o-mini")

search_a = agent(
    "search_a",
    prompt="List two facts about the topic from a historical angle.",
    llm=llm,
)
search_b = agent(
    "search_b", prompt="List two facts about the topic from a technical angle.", llm=llm
)
summarize = agent(
    "summarize",
    prompt="Merge these findings into a two-sentence brief.",
    takes=list,
    returns=str,
    llm=llm,
)

research = gather_all(search_a, search_b) + summarize
team: Flow[str, str] = embed(research, entry="task", out="summary")

frame = agent(
    "frame", prompt="Turn this brief into a precise research question.", llm=llm
)
report = agent(
    "report", prompt="Write a one-paragraph report from this research summary.", llm=llm
)


async def main() -> None:
    load_dotenv()
    pipeline = frame + team + report
    store = Store()
    stream = ReactiveExecutor().stream(
        pipeline.system(entry="brief", out="out"),
        store,
        seed=[Fact(tag="brief", value="the blackboard model in AI")],
        terminate=Goal(lambda v: v.exists("out")),
    )
    async for r in stream:
        print(f"step {r.step}: {r.fired} -> {[f.tag for f in r.writes]}")
    print("out:", store.snapshot().value("out"))


if __name__ == "__main__":
    asyncio.run(main())
