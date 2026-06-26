import asyncio

from fedotmas import Flow, action
from fedotmas.engine.contract import View

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


async def run(name: str, flow: Flow[dict, dict], seed: dict) -> None:
    print(name)
    async for r in flow.stream(seed):
        print(f"  step {r.step}: {r.fired} -> {[f.tag for f in r.writes]}")
    out = await flow.run(seed)
    assert out.ok, (out.reason, out.errors)
    print("  final:", out.value)


async def main() -> None:
    reflect = revise.loop(lambda s: s["quality"] >= THRESHOLD)
    await run("reflection: revise.loop(quality >= 3)", reflect, {"v": 0, "quality": 0})

    optimize = (generate + critique).loop(lambda s: s["approved"])
    await run(
        "eval-optimizer: (generate + critique).loop(approved)", optimize, {"n": 0}
    )


if __name__ == "__main__":
    asyncio.run(main())
