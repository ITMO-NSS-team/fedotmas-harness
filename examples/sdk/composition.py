import asyncio

from fedotmas.engine.contract import View
from fedotmas.sdk import Flow, action, gather


@action
async def research(topic: str, view: View) -> str:
    return f"facts about {topic}"


@action
async def write(facts: str, view: View) -> str:
    return f"draft from {facts}"


@action
async def edit(draft: str, view: View) -> str:
    return f"edited {draft}"


@action
async def upper(text: str, view: View) -> str:
    return text.upper()


@action
async def reverse(text: str, view: View) -> str:
    return text[::-1]


@action
async def combine(parts: list[str], view: View) -> str:
    return " | ".join(parts)


async def run(name: str, flow: Flow[str, str], value: str) -> None:
    print(name)
    async for r in flow.stream(value):
        print(f"  step {r.step}: {r.fired} -> {[f.tag for f in r.writes]}")
    out = await flow.run(value)
    assert out.ok, (out.reason, out.errors)
    print("  result:", out.value)


async def main() -> None:
    chain = research + write + edit
    await run("seq: research + write + edit", chain, "haiku")

    fanned = gather(upper, reverse) + combine
    await run("gather into seq: gather(upper, reverse) + combine", fanned, "abc")


if __name__ == "__main__":
    asyncio.run(main())
