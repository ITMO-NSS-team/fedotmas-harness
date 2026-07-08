import asyncio

from dotenv import load_dotenv
from fedotmas_llm import FunctionTool, LLMHooks, agent
from fedotmas_llm.adapters.pydantic_ai import PydanticAI


def add(a: int, b: int) -> int:
    return a + b


class TeamHooks(LLMHooks, surface=True):
    def on_handoff(self, frm, to, view, scope): ...


class Observe(TeamHooks):
    async def on_run_start(self, system):
        print("run:", len(system.nodes), "nodes")

    async def on_step(self, report):
        print("step:", report.fired)

    async def on_llm_request(self, call):
        print("llm <-", call.prompt)

    async def on_tool_call(self, tool, args):
        print("tool <-", tool.name, args)

    def on_handoff(self, frm, to):
        print("handoff:", frm, "->", to)


calc = agent(
    "calc",
    prompt="Use the add tool to sum the two numbers in the question.",
    tools=[FunctionTool("add", add)],
)


async def main() -> None:
    load_dotenv()
    await calc.run(
        "what is 17 plus 25?",
        bind={"llm": PydanticAI("openai-responses:gpt-4o-mini")},
        hooks=[Observe()],
    )


if __name__ == "__main__":
    asyncio.run(main())
