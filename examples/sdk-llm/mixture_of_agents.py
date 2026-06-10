"""Mixture-of-Agents (P7): layered parallel, aggregating between the layers.

Layer one fans the question to three different perspectives; an aggregator fuses them; layer
two refines the fused answer from three angles; a final aggregator settles it. Each layer is a
gather_all + a synthesizer, and the layers chain with +, so the whole stack is one typed arrow.

Needs an OpenAI key in .env. Run: uv run --group examples python examples/sdk-llm/mixture_of_agents.py
"""

import asyncio

from dotenv import load_dotenv

from fedotmas.adapters.pydantic_ai import PydanticAI
from fedotmas.engine.contract import Fact
from fedotmas.engine.executor import ReactiveExecutor
from fedotmas.engine.store import Store
from fedotmas.engine.terminate import Goal
from fedotmas.sdk import Flow, agent, gather_all

llm = PydanticAI("openai-responses:gpt-4o-mini")


def proposer(name: str, angle: str) -> Flow[str, str]:
    return agent(
        name,
        prompt=f"Answer the question from a {angle} angle, in two sentences.",
        llm=llm,
    )


def synth(name: str) -> Flow[list, str]:
    return agent(
        name,
        prompt="Fuse these candidate answers into one stronger answer.",
        takes=list,
        returns=str,
        llm=llm,
    )


async def main() -> None:
    load_dotenv()
    layer1 = gather_all(
        proposer("p1_practical", "practical"),
        proposer("p1_skeptical", "skeptical"),
        proposer("p1_historical", "historical"),
    )
    layer2 = gather_all(
        proposer("p2_clarify", "clarifying"),
        proposer("p2_counter", "counter-argument"),
        proposer("p2_concrete", "concrete-example"),
    )
    moa = layer1 + synth("synth1") + layer2 + synth("synth2")
    store = Store()
    stream = ReactiveExecutor().stream(
        moa.system(entry="question", out="answer"),
        store,
        seed=[
            Fact(
                tag="question",
                value="Should a small startup build its own agent framework?",
            )
        ],
        terminate=Goal(lambda v: v.exists("answer")),
    )
    async for r in stream:
        print(f"step {r.step}: {r.fired} -> {[f.tag for f in r.writes]}")
    print("answer:", store.snapshot().value("answer"))


if __name__ == "__main__":
    asyncio.run(main())
