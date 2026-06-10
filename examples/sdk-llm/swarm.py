"""Handoff / Swarm (P10): the active station handles, then names who is active next.

A branch inside a .loop. The body routes on the current station, the chosen specialist answers
and writes the next station into the threaded state, and the loop runs until a station marks the
ticket done. The handoff target is data in the state, so the route is decided each round rather
than wired at author time.

Needs an OpenAI key in .env. Run: uv run --group examples python examples/sdk-llm/swarm.py
"""

import asyncio

from dotenv import load_dotenv

from fedotmas.adapters.pydantic_ai import PydanticAI
from fedotmas.engine.contract import Fact, View
from fedotmas.engine.executor import ReactiveExecutor
from fedotmas.engine.store import Store
from fedotmas.engine.terminate import Budget, Goal
from fedotmas.sdk import action, branch

llm = PydanticAI("openai-responses:gpt-4o-mini")


@action
async def triage(s: dict, view: View) -> dict:
    reply = await llm.complete(
        "You are front-line triage. Restate the customer issue in one line.",
        s["ticket"],
        view,
    )
    return {**s, "log": [*s["log"], f"triage: {reply}"], "station": "billing"}


@action
async def billing(s: dict, view: View) -> dict:
    reply = await llm.complete(
        "You are billing support. Address any charge problem in one line.",
        s["ticket"],
        view,
    )
    return {**s, "log": [*s["log"], f"billing: {reply}"], "station": "tech"}


@action
async def tech(s: dict, view: View) -> dict:
    reply = await llm.complete(
        "You are technical support. Give one concrete fix for the crash.",
        s["ticket"],
        view,
    )
    return {**s, "log": [*s["log"], f"tech: {reply}"], "done": True}


async def main() -> None:
    load_dotenv()
    handle = branch(
        lambda s: s["station"], {"triage": triage, "billing": billing, "tech": tech}
    )
    swarm = handle.loop(lambda s: s.get("done", False))
    store = Store()
    stream = ReactiveExecutor().stream(
        swarm.system(entry="seed", out="final"),
        store,
        seed=[
            Fact(
                tag="seed",
                value={
                    "ticket": "I was double charged and now the app crashes on launch.",
                    "station": "triage",
                    "log": [],
                    "done": False,
                },
            )
        ],
        terminate=Goal(lambda v: v.exists("final")) | Budget(max_steps=12),
    )
    async for r in stream:
        print(f"step {r.step}: {r.fired} -> {[f.tag for f in r.writes]}")
    for line in store.snapshot().value("final")["log"]:
        print(" ", line)


if __name__ == "__main__":
    asyncio.run(main())
