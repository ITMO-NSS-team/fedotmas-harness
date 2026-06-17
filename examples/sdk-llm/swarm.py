import asyncio
from typing import Literal

from dotenv import load_dotenv
from fedotmas.adapters.pydantic_ai import PydanticAI
from fedotmas.sdk import agent, branch
from pydantic import BaseModel


class TriageNote(BaseModel):
    triage_note: str
    station: Literal["billing", "tech"]


class BillingNote(BaseModel):
    billing_note: str
    station: Literal["tech"]


class TechNote(BaseModel):
    tech_note: str
    done: bool


triage = agent(
    "triage",
    prompt=(
        "You are front-line triage. Restate the issue in one line as triage_note, and "
        "set station to the team that should act first: billing for charge problems, "
        "tech for crashes."
    ),
    input="{ticket}",
    takes=dict,
    returns=TriageNote,
).merge()

billing = agent(
    "billing",
    prompt=(
        "You are billing support. Resolve the charge problem in one line as "
        "billing_note, then hand the remaining technical issue to station tech."
    ),
    input="{ticket}",
    takes=dict,
    returns=BillingNote,
).merge()

tech = agent(
    "tech",
    prompt=(
        "You are technical support. Give one concrete fix for the crash as tech_note "
        "and set done to true."
    ),
    input="{ticket}",
    takes=dict,
    returns=TechNote,
).merge()

handle = branch("station", {"triage": triage, "billing": billing, "tech": tech})
swarm = handle.loop(until="done")


async def main() -> None:
    load_dotenv()
    run = await swarm.run(
        {
            "ticket": "I was double charged and now the app crashes on launch.",
            "station": "triage",
        },
        llm=PydanticAI("openai-responses:gpt-4o-mini"),
        budget=12,
    )
    for r in run.steps:
        print(f"step {r.step}: {r.fired} -> {[f.tag for f in r.writes]}")
    print("reason:", run.reason)
    for key in ("triage_note", "billing_note", "tech_note"):
        if run.value and key in run.value:
            print(f"  {key}: {run.value[key]}")


if __name__ == "__main__":
    asyncio.run(main())
