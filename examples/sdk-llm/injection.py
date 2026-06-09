"""Two different agent SDKs behind one seam, injected by name.

The `llm` parameter of agent is the LLM seam: a provider client or a whole framework wraps
into it. Here pydantic-ai and langchain each implement that one method, go into a dict keyed
by node name, and the composition references them. That dict is dependency injection, and it
is exactly the namespace consumer B's compiler hands its eval: the text expression names
symbols, the host supplies the backends. The prompt is still ours (authored on each agent),
the SDK is what swaps underneath. Bringing a whole self-contained foreign agent that owns its
own prompt is a different door, the as_agent extension point used throughout engine/.

Needs an OpenAI key in .env.
Run: uv run --group examples python examples/sdk-llm/injection.py
"""

import asyncio
from typing import Any

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

from fedotmas.adapters.pydantic_ai import PydanticAI
from fedotmas.engine.contract import Fact, View
from fedotmas.engine.executor import ReactiveExecutor
from fedotmas.engine.store import Store
from fedotmas.engine.terminate import Goal
from fedotmas.sdk import agent


class LangChain:
    """A user wrapping their own framework, langchain, into the LLM seam."""

    def __init__(self, model: str) -> None:
        self._llm = ChatOpenAI(model=model)

    async def complete(
        self, prompt: str, input: Any, view: View, returns: type = str
    ) -> Any:
        reply = await self._llm.ainvoke([("system", prompt), ("human", str(input))])
        return reply.content


async def main() -> None:
    load_dotenv()
    backends = {
        "summarize": PydanticAI("openai-responses:gpt-4o-mini"),
        "translate": LangChain("gpt-4o-mini"),
    }
    summarize = agent(
        "summarize",
        prompt="Summarize the text in one sentence.",
        llm=backends["summarize"],
    )
    translate = agent(
        "translate",
        prompt="Translate the text to French.",
        llm=backends["translate"],
    )
    pipeline = summarize + translate
    store = Store()
    stream = ReactiveExecutor().stream(
        pipeline.system(entry="text", out="out"),
        store,
        seed=[
            Fact(tag="text", value="A blackboard lets agents activate on shared facts.")
        ],
        terminate=Goal(lambda v: v.exists("out")),
    )
    async for r in stream:
        print(f"step {r.step}: {r.fired} -> {[f.tag for f in r.writes]}")
    print("out:", store.snapshot().value("out"))


if __name__ == "__main__":
    asyncio.run(main())
