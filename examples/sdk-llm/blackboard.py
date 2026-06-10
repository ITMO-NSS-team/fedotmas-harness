"""Blackboard (P13): rules self-activate on conditions, no fixed topology.

The rule surface, not the arrow surface. Three rules use the produce-once default (fire when
the read fact is present and the written one is not yet), so they need no explicit trigger. But
this is a real blackboard, not a disguised chain: `researcher` and `skeptic` both wake on the
same hypothesis and run in parallel, and `verifier` waits on two independent facts at once, a
condition not reducible to one read, so it spells out `when`. The order falls out of the facts.

Needs an OpenAI key in .env. Run: uv run --group examples python examples/sdk-llm/blackboard.py
"""

import asyncio

from dotenv import load_dotenv

from fedotmas.adapters.pydantic_ai import PydanticAI
from fedotmas.engine.contract import Fact, View
from fedotmas.engine.executor import ReactiveExecutor
from fedotmas.engine.store import Store
from fedotmas.engine.terminate import Goal
from fedotmas.sdk import Rule, blackboard

llm = PydanticAI("openai-responses:gpt-4o-mini")


async def hypothesize(question: str, view: View) -> str:
    return await llm.complete(
        "Propose one testable hypothesis answering the question.", question, view
    )


async def research(hypothesis: str, view: View) -> str:
    return await llm.complete(
        "State one piece of evidence that supports this hypothesis.", hypothesis, view
    )


async def doubt(hypothesis: str, view: View) -> str:
    return await llm.complete(
        "Raise one serious objection to this hypothesis.", hypothesis, view
    )


async def verify(evidence: str, view: View) -> str:
    objection = view.value("objection")
    return await llm.complete(
        "Weigh the evidence against the objection and give a one-line conclusion.",
        f"Evidence: {evidence}\nObjection: {objection}",
        view,
    )


async def main() -> None:
    load_dotenv()
    investigation = blackboard(
        Rule("hypothesizer", hypothesize, writes="hypothesis", reads="question"),
        Rule("researcher", research, writes="evidence", reads="hypothesis"),
        Rule("skeptic", doubt, writes="objection", reads="hypothesis"),
        Rule(
            "verifier",
            verify,
            writes="conclusion",
            reads="evidence",
            when=lambda v: v.exists("evidence")
            and v.exists("objection")
            and not v.exists("conclusion"),
        ),
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
