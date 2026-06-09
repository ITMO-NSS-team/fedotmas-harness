"""Iteration as a typed arrow: .loop threads state until a predicate clears.

Reflection (P15) and Evaluator-Optimizer (P6) are the same loop. The body is a Flow[S, S]
run each round as an isolated sub-system; .loop is only valid when input and output types
match, so the state contract is checked. The predicate reads that state value.
"""

import asyncio

from fedotmas.sdk import action
from fedotmas.engine.contract import Fact, View
from fedotmas.engine.executor import ReactiveExecutor
from fedotmas.engine.store import Store
from fedotmas.engine.terminate import Budget, Goal

THRESHOLD = 3


@action
async def revise(draft: dict, view: View) -> dict:
    n = draft["v"] + 1
    return {"v": n, "quality": n}


@action
async def generate(prev: dict, view: View) -> dict:
    n = prev["n"] + 1
    return {"n": n, "quality": n}


@action
async def critique(draft: dict, view: View) -> dict:
    return {**draft, "approved": draft["quality"] >= THRESHOLD}


async def run(name: str, system, seed: Fact, out: str) -> None:
    store = Store()
    stream = ReactiveExecutor().stream(
        system, store, seed=[seed], terminate=Goal(lambda v: v.exists(out)) | Budget(20)
    )
    print(name)
    async for r in stream:
        print(f"  step {r.step}: {r.fired} -> {[f.tag for f in r.writes]}")
    print(f"  {out}:", store.snapshot().value(out))


async def main() -> None:
    reflect = revise.loop(lambda s: s["quality"] >= THRESHOLD)
    await run(
        "reflection: revise.loop(quality >= 3)",
        reflect.system(entry="seed", out="final"),
        Fact(tag="seed", value={"v": 0, "quality": 0}),
        "final",
    )

    optimize = (generate + critique).loop(lambda s: s["approved"])
    await run(
        "eval-optimizer: (generate + critique).loop(approved)",
        optimize.system(entry="seed", out="final"),
        Fact(tag="seed", value={"n": 0}),
        "final",
    )


if __name__ == "__main__":
    asyncio.run(main())
