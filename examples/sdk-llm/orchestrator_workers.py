"""Orchestrator-Workers (P9): the width is decided at runtime by the planner.

A planner agent returns a structured plan whose length it chooses; a worker action fans the
model over however many subtasks came back (real per-item concurrency via asyncio.gather);
a synthesizer folds the results. gather (the operator) is fixed-width at author time, so
runtime-sized fan-out lives inside an action, not in the arrow shape.

Needs an OpenAI key in .env. Run: uv run --group examples python examples/sdk-llm/orchestrator_workers.py
"""

import asyncio

from dotenv import load_dotenv
from pydantic import BaseModel

from fedotmas.adapters.pydantic_ai import PydanticAI
from fedotmas.engine.contract import Fact, View
from fedotmas.engine.executor import ReactiveExecutor
from fedotmas.engine.store import Store
from fedotmas.engine.terminate import Goal
from fedotmas.sdk import action, agent

llm = PydanticAI("openai-responses:gpt-4o-mini")


class Plan(BaseModel):
    subtasks: list[str]


plan = agent(
    "planner",
    prompt="Break the goal into 2-4 independent subtasks.",
    takes=str,
    returns=Plan,
    llm=llm,
)
synthesize = agent(
    "synthesize",
    prompt="Combine these subtask results into one final report.",
    takes=list,
    returns=str,
    llm=llm,
)


@action
async def work(plan: Plan, view: View) -> list[str]:
    async def one(task: str) -> str:
        return await llm.complete("Carry out this subtask in one sentence.", task, view)

    return list(await asyncio.gather(*(one(s) for s in plan.subtasks)))


async def main() -> None:
    load_dotenv()
    pipeline = plan + work + synthesize
    store = Store()
    stream = ReactiveExecutor().stream(
        pipeline.system(entry="goal", out="report"),
        store,
        seed=[
            Fact(
                tag="goal",
                value="plan a one-day launch for a small open-source library",
            )
        ],
        terminate=Goal(lambda v: v.exists("report")),
    )
    async for r in stream:
        print(f"step {r.step}: {r.fired} -> {[f.tag for f in r.writes]}")
    print("report:", store.snapshot().value("report"))


if __name__ == "__main__":
    asyncio.run(main())
