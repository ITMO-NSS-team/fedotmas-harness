"""Blackboard: declarative prompt rules self-activate on conditions, no fixed topology.

Every rule here is a prompt, not code: Rule(prompt=...) is the rule-surface twin of the agent
atom, with the backend bound once at blackboard(). researcher and skeptic both wake on the
same hypothesis and run in parallel; verifier waits on two independent facts at once, a
condition not reducible to one read, so it spells out `when`, and its `input` template pulls
both facts from the store by tag. The order falls out of the facts. The blackboard runs
directly on the engine, the surface arrows cannot express this shape.

Needs an OpenAI key in .env. Run: uv run --group examples python examples/sdk-llm/blackboard.py
"""

import asyncio

from dotenv import load_dotenv

from fedotmas.adapters.pydantic_ai import PydanticAI
from fedotmas.engine.contract import Fact
from fedotmas.engine.executor import ReactiveExecutor
from fedotmas.engine.store import Store
from fedotmas.engine.terminate import Goal
from fedotmas.sdk import Rule, blackboard


async def main() -> None:
    load_dotenv()
    investigation = blackboard(
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
            when=lambda v: v.exists("evidence")
            and v.exists("objection")
            and not v.exists("conclusion"),
        ),
        llm=PydanticAI("openai-responses:gpt-4o-mini"),
    )
    store = Store()
    stream = ReactiveExecutor().stream(
        investigation,
        store,
        seed=[
            Fact(
                tag="question",
                value="why do blackboard systems suit open-ended problems?",
            )
        ],
        terminate=Goal(lambda v: v.exists("conclusion")),
    )
    async for r in stream:
        print(f"step {r.step}: {r.fired} -> {[f.tag for f in r.writes]}")
    print("conclusion:", store.snapshot().value("conclusion"))


if __name__ == "__main__":
    asyncio.run(main())
