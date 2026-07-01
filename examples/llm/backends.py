import asyncio
from typing import Any

from dotenv import load_dotenv
from fedotmas import action, gather
from fedotmas.engine.contract import View
from fedotmas_llm import Call, agent
from fedotmas_llm.adapters.pydantic_ai import PydanticAI
from langchain.chat_models import init_chat_model
from langchain_core.messages import HumanMessage, SystemMessage

load_dotenv()


class LangChain:
    """An easy way to use a different SDK"""

    def __init__(self, model: str) -> None:
        self._model = init_chat_model(model)

    async def complete(self, call: Call, view: View) -> Any:
        messages = [SystemMessage(call.prompt), HumanMessage(str(call.input))]
        reply = await self._model.ainvoke(messages)
        return reply.content


summarize = agent("summarize", prompt="Summarize the text in two sentences.")

headline = agent(
    "headline",
    prompt="Write one short, punchy headline for the text. No quotes.",
    llm=LangChain("openai:gpt-4o-mini"),
)


@action
async def assemble(parts: list[str], view: View) -> str:
    summary, title = parts
    return f"# {title}\n\n{summary}"


system = gather(summarize, headline) + assemble

TEXT = (
    "The same orchestration engine can host agents written against different frameworks, "
    "because each agent is a black box behind one call seam: the engine schedules facts "
    "and triggers, and never learns whose SDK produced the reply."
)


async def main() -> None:
    run = await system.run(
        TEXT, bind={"llm": PydanticAI("openai-responses:gpt-4o-mini")}, budget=8
    )
    for r in run.steps:
        print(f"step {r.step}: {r.fired} -> {[f.tag for f in r.writes]}")
    print("reason:", run.reason)
    print(run.value)


if __name__ == "__main__":
    asyncio.run(main())
