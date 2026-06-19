import asyncio

from dotenv import load_dotenv
from fedotmas.sdk import Rule, blackboard
from fedotmas_llm.adapters.pydantic_ai import PydanticAI


async def main() -> None:
    load_dotenv()
    board = blackboard(
        Rule(
            "hypothesizer",
            prompt="Propose one testable hypothesis answering the question.",
            reads="question",
            writes="hypothesis",
        ),
        Rule(
            "researcher",
            prompt="State one piece of evidence that supports this hypothesis.",
            reads="hypothesis",
            writes="evidence",
        ),
        Rule(
            "skeptic",
            prompt="Raise one serious objection to this hypothesis.",
            reads="hypothesis",
            writes="objection",
        ),
        Rule(
            "verifier",
            prompt="Weigh the evidence against the objection and give a one-line conclusion.",
            input="Evidence: {evidence}\nObjection: {objection}",
            reads="evidence",
            writes="conclusion",
            when=["evidence", "objection", "!conclusion"],
        ),
        llm=PydanticAI("openai-responses:gpt-4o-mini"),
    )
    run = await board.run(
        {"question": "why do blackboard systems suit open-ended problems?"},
        goal="conclusion",
        budget=8,
    )
    for r in run.steps:
        print(f"step {r.step}: {r.fired} -> {[f.tag for f in r.writes]}")
    print("reason:", run.reason)
    print("conclusion:", run.value)


if __name__ == "__main__":
    asyncio.run(main())
