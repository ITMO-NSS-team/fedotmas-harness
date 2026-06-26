import asyncio
from collections.abc import Awaitable, Callable

from fedotmas.engine import as_node
from fedotmas.engine.contract import Fact, Result, View
from fedotmas.engine.executor import ReactiveExecutor
from fedotmas.engine.store import Store
from fedotmas.engine.system import System
from fedotmas.engine.terminate import Goal

ROUTES = {"triage": "billing", "billing": "tech", "tech": None}


def station(name: str, nxt: str | None) -> Callable[[object, View], Awaitable[Result]]:
    async def run(input: object, view: View) -> Result:
        writes = [Fact(tag=f"log:{name}", value=f"{name} handled")]
        writes.append(
            Fact(tag="active", value=nxt) if nxt else Fact(tag="done", value=True)
        )
        return Result(writes=writes)

    return run


def is_active(name: str) -> Callable[[View], bool]:
    return lambda v: v.value("active") == name


async def main() -> None:
    system = System(
        nodes=[
            as_node(station(n, nxt), name=n, reads="active", trigger=is_active(n))
            for n, nxt in ROUTES.items()
        ]
    )
    store = Store()
    stream = ReactiveExecutor().stream(
        system,
        store,
        seed=[Fact(tag="active", value="triage")],
        terminate=Goal(lambda v: v.exists("done")),
    )
    async for r in stream:
        print(f"step {r.step}: {r.fired} -> {[f.tag for f in r.writes]}")
    print("path:", [f.tag for f in store.snapshot().query("log:*")])


if __name__ == "__main__":
    asyncio.run(main())
