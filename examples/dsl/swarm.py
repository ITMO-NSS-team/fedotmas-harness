"""Handoff / Swarm as data: the manifest spelling of sdk-llm/swarm.py.

Every station is a prompted node over the dict state: an input template picks the ticket
out, takes is dict, and the structured reply folds back in via step/merge — the handoff
target rides inside the reply. The branch routes by the state key, the loop stops on a
state key. The Literal constraint on station lives in the registered models: types= carries
what the inline field vocabulary cannot.

Needs an OpenAI key in .env. Run: uv run --group examples python examples/dsl/swarm.py
"""

import asyncio
from typing import Literal

from dotenv import load_dotenv
from pydantic import BaseModel

from fedotmas import dsl
from fedotmas.adapters.pydantic_ai import PydanticAI


class TriageNote(BaseModel):
    triage_note: str
    station: Literal["billing", "tech"]


class BillingNote(BaseModel):
    billing_note: str
    station: Literal["tech"]


class TechNote(BaseModel):
    tech_note: str
    done: bool


MANIFEST = {
    "version": 1,
    "meta": {"name": "support-swarm", "intent": "route a ticket between stations"},
    "nodes": {
        "triage": {
            "prompt": (
                "You are front-line triage. Restate the issue in one line as "
                "triage_note, and set station to the team that should act first: "
                "billing for charge problems, tech for crashes."
            ),
            "input": "{ticket}",
            "takes": "dict",
            "returns": "TriageNote",
        },
        "billing": {
            "prompt": (
                "You are billing support. Resolve the charge problem in one line as "
                "billing_note, then hand the remaining technical issue to station tech."
            ),
            "input": "{ticket}",
            "takes": "dict",
            "returns": "BillingNote",
        },
        "tech": {
            "prompt": (
                "You are technical support. Give one concrete fix for the crash as "
                "tech_note and set done to true."
            ),
            "input": "{ticket}",
            "takes": "dict",
            "returns": "TechNote",
        },
    },
    "flow": {
        "loop": {
            "branch": "station",
            "cases": {
                "triage": {"step": "triage", "merge": True},
                "billing": {"step": "billing", "merge": True},
                "tech": {"step": "tech", "merge": True},
            },
        },
        "until": "done",
    },
}

swarm = dsl.compile(
    dsl.Manifest.model_validate(MANIFEST),
    types={"TriageNote": TriageNote, "BillingNote": BillingNote, "TechNote": TechNote},
)


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
