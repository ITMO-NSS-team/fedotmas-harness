import asyncio

from dotenv import load_dotenv
from fedotmas.engine.contract import View
from fedotmas.sdk import action, agent
from fedotmas_llm.adapters.pydantic_ai import PydanticAI
from pydantic import BaseModel

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
