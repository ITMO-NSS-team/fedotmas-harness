import asyncio
from typing import Any

from fedotmas.engine.contract import View
from fedotmas_llm import Call
from fedotmas_meta import Recipe, Review
from fedotmas_meta.selector import drafted, frozen, pipeline


class StubSelector:
    """The small trained model: task in, recipe coordinates out."""

    async def complete(self, call: Call, view: View) -> Any:
        return Recipe(decompose="master")


class StubAssembler:
    """The frontier model: writes a prompt per role of the chosen structure."""

    async def complete(self, call: Call, view: View) -> Any:
        return call.returns(
            **{
                name: f"You are the {name}. Be brief."
                if field.annotation is str
                else {"extract": "Pull out the facts.", "compute": "Do the math."}
                for name, field in call.returns.model_fields.items()
            }
        )


class StubExecutor:
    """The weak model the built system runs on."""

    async def complete(self, call: Call, view: View) -> Any:
        if call.returns is Review:
            return Review(approved=True, feedback="ok")
        return f"[{call.prompt}] {str(call.input)[:60]}"


# Hand-written prompts per menu cell: the reproducible fill source.
FILLS = {
    "single": {"agent": "Answer directly and briefly."},
    "orchestrator": {
        "planner": "Split the task into two independent parts.",
        "workers": {"extract": "Pull out the facts.", "compute": "Do the math."},
        "synthesizer": "Merge the parts into one answer.",
    },
}


async def main() -> None:
    task = "A train covers 300 km in 4 hours. How far in 7?"
    for source in (frozen(FILLS), drafted(StubAssembler())):
        flow = pipeline(selector=StubSelector(), executor=StubExecutor(), fills=source)
        run = await flow.run(task)
        print("reason:", run.reason)
        print("answer:", run.value)


if __name__ == "__main__":
    asyncio.run(main())
