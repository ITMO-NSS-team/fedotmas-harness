"""DAG with a parallel block: extract, argue both sides at once, then weigh.

The arrow algebra on stateless str -> str nodes: + is sequence, gather runs branches in
parallel and lists their outputs for the next stage. No node names a backend; the llm binds once as the
default at .run(), which also derives the store, the seed, and the terminate condition, and
hands back an Outcome: .value, .ok, .reason, and the full .steps trace.

Needs an OpenAI key in .env. Run: uv run --group examples python examples/sdk-llm/dag.py
"""

import asyncio

from dotenv import load_dotenv

from fedotmas.adapters.pydantic_ai import PydanticAI
from fedotmas.sdk import agent, gather

extract = agent(
    "extract", prompt="Extract the central claim of the text in one sentence."
)
support = agent("support", prompt="Give the single strongest argument FOR the claim.")
oppose = agent("oppose", prompt="Give the single strongest argument AGAINST the claim.")
balance = agent(
    "balance",
    prompt="You get a [for, against] list of arguments. Weigh them and give a one-sentence verdict.",
    takes=list,
    returns=str,
)

dag = extract + gather(support, oppose) + balance

TEXT = (
    "Multi-agent systems should be compiled from a declarative spec rather than "
    "hand-wired, because a spec can be generated, checked, and repaired by a machine."
)


async def main() -> None:
    load_dotenv()
    run = await dag.run(TEXT, llm=PydanticAI("openai-responses:gpt-4o-mini"), budget=8)
    for r in run.steps:
        print(f"step {r.step}: {r.fired} -> {[f.tag for f in r.writes]}")
    print("reason:", run.reason)
    print("verdict:", run.value)


if __name__ == "__main__":
    asyncio.run(main())
