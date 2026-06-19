"""Select a pattern for the task, fill its roles, run the built system."""

import asyncio

from dotenv import load_dotenv
from fedotmas_llm.adapters.pydantic_ai import PydanticAI
from fedotmas_meta.presets import get
from fedotmas_meta.selector import select

TASK = "Should the city ban cars from the center? Give a balanced recommendation."

FILL = {
    "pro": "Argue for the proposal as strongly as the facts allow.",
    "con": "Attack the proposal; find its weakest assumptions.",
    "judge": "Weigh both sides and give one recommendation.",
}


async def main() -> None:
    load_dotenv()
    llm = PydanticAI("openai-responses:gpt-4o-mini")

    picked = await select(TASK, llm=llm)
    print(f"selected: {picked.pattern}")
    # the fill stage is the meta-agent's next job; this hand fill matches debate
    assert picked.pattern == "debate"

    run = await get(picked.pattern).build(FILL).run(TASK, llm=llm)
    print(run.value)


if __name__ == "__main__":
    asyncio.run(main())
