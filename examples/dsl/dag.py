"""DAG with a parallel block, as data: the manifest spelling of sdk-llm/dag.py.

Bare strings are prompts, a list is a sequence, gather is the parallel block, and a named
flow splices in by name. dsl.compile turns the document into the same Flow the Python
spelling builds; the llm still binds at .run().

Needs an OpenAI key in .env. Run: uv run --group examples python examples/dsl/dag.py
"""

import asyncio

from dotenv import load_dotenv

from fedotmas import dsl
from fedotmas.adapters.pydantic_ai import PydanticAI

MANIFEST = {
    "version": 1,
    "meta": {"name": "claim-debate", "intent": "weigh a text's central claim"},
    "nodes": {
        "extract": "Extract the central claim of the text in one sentence.",
        "support": "Give the single strongest argument FOR the claim.",
        "oppose": "Give the single strongest argument AGAINST the claim.",
        "balance": (
            "You get a [for, against] pair of arguments. Weigh them and give a "
            "one-sentence verdict."
        ),
    },
    "flows": {"debate": {"gather": ["support", "oppose"]}},
    "flow": ["extract", "debate", "balance"],
}

dag = dsl.compile(dsl.Manifest.model_validate(MANIFEST))

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
