import asyncio

from fedotmas.engine import as_node
from fedotmas.engine.contract import Fact, Result, View
from fedotmas.engine.executor import ReactiveExecutor
from fedotmas.engine.store import Store
from fedotmas.engine.system import System
from fedotmas.engine.terminate import Goal


async def research(input: object, view: View) -> Result:
    return Result(writes=[Fact(tag="research", value="raw facts")])


async def write(input: object, view: View) -> Result:
    return Result(
        writes=[Fact(tag="draft", value=f"draft from {view.value('research')}")]
    )


async def edit(input: object, view: View) -> Result:
    return Result(writes=[Fact(tag="final", value=f"edited {view.value('draft')}")])


async def main() -> None:
    system = System(
        nodes=[
            as_node(research, name="researcher", reads="topic"),
            as_node(write, name="writer", reads="research"),
            as_node(edit, name="editor", reads="draft"),
        ]
    )
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
