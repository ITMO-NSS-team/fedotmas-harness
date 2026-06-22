import asyncio

from fedotmas import Flow, action, gather

# The trailing `view` of an action body is optional: drop it when the body does not read
# the store. Add `view: View` (from fedotmas.engine.contract) back when a body needs it.


@action
async def research(topic: str) -> str:
    return f"facts about {topic}"


@action
async def write(facts: str) -> str:
    return f"draft from {facts}"


@action
async def edit(draft: str) -> str:
    return f"edited {draft}"


@action
async def upper(text: str) -> str:
    return text.upper()


@action
async def reverse(text: str) -> str:
    return text[::-1]


@action
async def combine(parts: list[str]) -> str:
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
