"""Reflection (P15): one agent revises its own output until it clears a bar.

Same loop as Evaluator-Optimizer, with the critic folded into the generator.
"""

import asyncio

from fedotmas.adapters import as_agent
from fedotmas.engine.contract import Fact, Result, View
from fedotmas.engine.executor import ReactiveExecutor
from fedotmas.engine.store import Store
from fedotmas.engine.system import System
from fedotmas.engine.terminate import Goal

THRESHOLD = 3


async def revise(input: object, view: View) -> Result:
    n = view.count("draft:*") + 1
    return Result(
        writes=[Fact(tag=f"draft:{n}", value={"text": f"v{n}", "quality": n})]
    )


def below_bar(v: View) -> bool:
    drafts = v.query("draft:*")
    return not drafts or drafts[-1].value["quality"] < THRESHOLD


async def main() -> None:
    system = System(
        agents=[as_agent(revise, name="reviser", reads="draft:*", trigger=below_bar)]
    )
    store = Store()
    stream = ReactiveExecutor().stream(
        system,
        store,
        seed=[Fact(tag="task", value="write a tagline")],
        terminate=Goal(lambda v: not below_bar(v)),
    )
    async for r in stream:
        print(f"step {r.step}: {r.fired} -> {[f.tag for f in r.writes]}")
    print("final draft:", store.snapshot().query("draft:*")[-1].value)


if __name__ == "__main__":
    asyncio.run(main())
