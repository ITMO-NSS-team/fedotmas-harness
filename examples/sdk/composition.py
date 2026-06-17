"""Typed arrows compose where the flat combinators could not.

Two fragments built from the same atoms, stitched by operators. The parallel block feeds
a sequential stage (`gather` then `+`), the case the flat parallel/join could not nest. The
types make the stitch checkable: combine must accept list[str], the gathered output.
"""

import asyncio

from fedotmas.sdk import action, gather
from fedotmas.engine.contract import Fact, View
from fedotmas.engine.executor import ReactiveExecutor
from fedotmas.engine.store import Store
from fedotmas.engine.terminate import Goal


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


async def run(name: str, system, seed: Fact, out: str) -> None:
    store = Store()
    stream = ReactiveExecutor().stream(
        system, store, seed=[seed], terminate=Goal(lambda v: v.exists(out))
    )
    print(name)
    async for r in stream:
        print(f"  step {r.step}: {r.fired} -> {[f.tag for f in r.writes]}")
    print(f"  {out}:", store.snapshot().value(out))


async def main() -> None:
    chain = research + write + edit
    await run(
        "seq: research + write + edit",
        chain.system(entry="topic", out="final"),
        Fact(tag="topic", value="haiku"),
        "final",
    )

    fanned = gather(upper, reverse) + combine
    await run(
        "gather into seq: gather(upper, reverse) + combine",
        fanned.system(entry="text", out="result"),
        Fact(tag="text", value="abc"),
        "result",
    )


if __name__ == "__main__":
    asyncio.run(main())
