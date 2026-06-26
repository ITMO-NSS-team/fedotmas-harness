import asyncio

from fedotmas import Flow, action, branch


@action
async def draft(state: dict) -> str:
    return f"draft of {state['topic']}"


@action
async def classify(state: dict) -> dict:
    return {"team": "support", "priority": "high"}


@action
async def triage(state: dict) -> dict:
    return {**state, "action": "triaged"}


@action
async def plan(state: dict) -> dict:
    return {**state, "action": "planned"}


@action
async def revise(state: dict) -> dict:
    n = state["round"] + 1
    return {**state, "round": n, "done": n >= 2}


async def run(name: str, flow: Flow[dict, dict], seed: dict) -> None:
    print(name)
    out = await flow.run(seed)
    assert out.ok, (out.reason, out.errors)
    print("  ", out.value)


async def main() -> None:
    await run(
        "into: output under a key, rest passes through",
        draft.into("draft"),
        {"topic": "tea"},
    )
    await run(
        "merge: fold a structured reply into the state",
        classify.merge(),
        {"ticket": "x"},
    )
    await run(
        "branch by state key",
        branch("kind", {"bug": triage, "feature": plan}),
        {"kind": "bug"},
    )
    await run("loop until state key", revise.loop(until="done"), {"round": 0})


if __name__ == "__main__":
    asyncio.run(main())
