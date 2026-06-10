"""Master orchestrator: a planner sizes the work at runtime, workers fan out, one report back.

The planner is an agent with structured output, so the plan's width is the model's choice,
not the author's. The fan-out over that runtime-sized plan is the one place the declarative
atoms do not reach, so it is an action, the code escape hatch, with real per-subtask
concurrency via asyncio.gather; the synthesizer folds the results back to one report. LLM
nodes bind the default backend at .run(); the action closes over the same client directly.

Needs an OpenAI key in .env. Run: uv run --group examples python examples/sdk-llm/orchestrator.py
"""

import asyncio

from dotenv import load_dotenv
from pydantic import BaseModel

from fedotmas.adapters.pydantic_ai import PydanticAI
from fedotmas.engine.contract import View
from fedotmas.sdk import action, agent

llm = PydanticAI("openai-responses:gpt-4o-mini")


class Plan(BaseModel):
    subtasks: list[str]


plan = agent(
    "planner",
    prompt="Break the goal into 2-4 independent subtasks.",
    takes=str,
    returns=Plan,
)

synthesize = agent(
    "synthesize",
    prompt="Combine these subtask results into one final report.",
    takes=list,
    returns=str,
)


@action
async def work(p: Plan, view: View) -> list[str]:
    async def one(task: str) -> str:
        return await llm.complete("Carry out this subtask in one sentence.", task, view)

    return list(await asyncio.gather(*(one(s) for s in p.subtasks)))


orchestrator = plan + work + synthesize


async def main() -> None:
    load_dotenv()
    run = await orchestrator.run(
        "plan a one-day launch for a small open-source library", llm=llm, budget=8
    )
    for r in run.steps:
        print(f"step {r.step}: {r.fired} -> {[f.tag for f in r.writes]}")
    print("reason:", run.reason)
    print("report:", run.value)


if __name__ == "__main__":
    asyncio.run(main())
