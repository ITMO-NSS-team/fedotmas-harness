import asyncio

from dotenv import load_dotenv
from fedotmas import dsl
from fedotmas_llm import agent
from fedotmas_llm.adapters.pydantic_ai import PydanticAI

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

dag = dsl.compile(dsl.Manifest.model_validate(MANIFEST), providers={"agent": agent})

TEXT = (
    "Multi-agent systems should be compiled from a declarative spec rather than "
    "hand-wired, because a spec can be generated, checked, and repaired by a machine."
)


async def main() -> None:
    load_dotenv()
    run = await dag.run(
        TEXT, bind={"llm": PydanticAI("openai-responses:gpt-4o-mini")}, budget=8
    )
    for r in run.steps:
        print(f"step {r.step}: {r.fired} -> {[f.tag for f in r.writes]}")
    print("reason:", run.reason)
    print("verdict:", run.value)


if __name__ == "__main__":
    asyncio.run(main())
