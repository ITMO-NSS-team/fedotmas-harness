import asyncio

from fedotmas.engine.contract import Fact, View
from fedotmas.engine.executor import ReactiveExecutor
from fedotmas.engine.store import Store
from fedotmas.engine.terminate import Goal
from fedotmas.sdk import action, branch


def classify(q: str) -> str:
    if q[0].isdigit():
        return "math"
    if q.endswith("?"):
        return "prose"
    return "code"


@action
async def solve(q: str, view: View) -> str:
    return f"{q} = 4"


@action
async def write(q: str, view: View) -> str:
    return f"prose for {q}"


@action
async def code(q: str, view: View) -> str:
    return f"def f(): ...  # {q}"


async def run(q: str) -> None:
    router = branch(classify, {"math": solve, "prose": write, "code": code})
    store = Store()
    stream = ReactiveExecutor().stream(
        router.system(entry="q", out="answer"),
        store,
        seed=[Fact(tag="q", value=q)],
        terminate=Goal(lambda v: v.exists("answer")),
    )
    print(f"q = {q!r}")
    async for r in stream:
        print(f"  step {r.step}: {r.fired} -> {[f.tag for f in r.writes]}")
    print("  answer:", store.snapshot().value("answer"))


async def main() -> None:
    await run("2 + 2")
    await run("what is a haiku?")
    await run("sort a list")


if __name__ == "__main__":
    asyncio.run(main())
