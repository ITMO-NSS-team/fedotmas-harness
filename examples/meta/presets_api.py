import asyncio

from _presets import CATALOG
from dotenv import load_dotenv
from fedotmas_llm.adapters.pydantic_ai import PydanticAI
from fedotmas_meta import AgentSpec, SystemSpec, assemble, select

TASK = "Should the city ban cars from the center? Give a balanced recommendation."

# the fill stage is the meta-agent's next job; this hand fill matches the debate preset
PROPOSAL = SystemSpec(
    preset="debate",
    fill={
        "voters": {
            "pro": AgentSpec(
                prompt="Argue for the proposal as strongly as the facts allow."
            ),
            "con": AgentSpec(
                prompt="Attack the proposal; find its weakest assumptions."
            ),
        },
        "judge": AgentSpec(prompt="Weigh both sides and give one recommendation."),
    },
)


async def main() -> None:
    load_dotenv()
    llm = PydanticAI("openai-responses:gpt-4o-mini")

    picked = await select(TASK, presets=CATALOG, llm=llm)
    print(f"selected: {picked.pattern}")
    assert picked.pattern == "debate"

    run = await assemble(PROPOSAL, presets=CATALOG).run(TASK, bind={"llm": llm})
    print(run.value)


if __name__ == "__main__":
    asyncio.run(main())
