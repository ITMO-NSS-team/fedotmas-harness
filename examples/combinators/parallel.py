"""parallel/join: branches fan out from one input, join reduces them back to one value.

Same shape as the hand-written engine/sectioning.py: fan-out plus a count-gated join.
The combinator owns the branch tags, the distinct branch identities, and the join trigger.
"""

import asyncio

from fedotmas.dsl.combinators import parallel
from fedotmas.engine.contract import Fact, View
from fedotmas.engine.executor import ReactiveExecutor
from fedotmas.engine.store import Store
from fedotmas.engine.terminate import Goal


async def upper(input: str, view: View) -> str:
    return input.upper()


async def reverse(input: str, view: View) -> str:
    return input[::-1]


async def repeat(input: str, view: View) -> str:
    return input * 2


async def combine(parts: list[str], view: View) -> str:
    return " | ".join(parts)


async def main() -> None:
    system = parallel(upper, reverse, repeat, join=combine, entry="text", out="result")
    store = Store()
    stream = ReactiveExecutor().stream(
        system,
        store,
        seed=[Fact(tag="text", value="abc")],
        terminate=Goal(lambda v: v.exists("result")),
    )
    async for r in stream:
        print(f"step {r.step}: {r.fired} -> {[f.tag for f in r.writes]}")
    print("result:", store.snapshot().value("result"))


if __name__ == "__main__":
    asyncio.run(main())
