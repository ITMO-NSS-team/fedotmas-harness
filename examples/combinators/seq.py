"""seq combinator: steps return plain values, the combinator owns tags and wiring.

Same run as the hand-written prompt_chaining.py, final fact is identical.
"""

import asyncio

from fedotmas.dsl.combinators import seq
from fedotmas.engine.contract import Fact, View
from fedotmas.engine.executor import ReactiveExecutor
from fedotmas.engine.store import Store
from fedotmas.engine.terminate import Goal


async def research(input: object, view: View) -> str:
    return "raw facts"


async def write(input: object, view: View) -> str:
    return f"draft from {input}"


async def edit(input: object, view: View) -> str:
    return f"edited {input}"


async def main() -> None:
    system = seq(research, write, edit, entry="topic", out="final")
    store = Store()
    stream = ReactiveExecutor().stream(
        system,
        store,
        seed=[Fact(tag="topic", value="witcher")],
        terminate=Goal(lambda v: v.exists("final")),
    )
    async for r in stream:
        print(f"step {r.step}: {r.fired} -> {[f.tag for f in r.writes]}")
    print("final:", store.snapshot().value("final"))


if __name__ == "__main__":
    asyncio.run(main())
