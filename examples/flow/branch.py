"""Router (P8) as a typed arrow: branch picks one case by a label, exactly one fires.

select returns the case key; only that case's sub-flow is fed an input fact, so only its
chain runs and converges to the branch output. Every case is a Flow[A, B] with the same
boundary, so the cases are interchangeable by type and each is itself composable.
"""

import asyncio

from fedotmas.dsl.flow import action, branch
from fedotmas.engine.contract import Fact, View
from fedotmas.engine.executor import ReactiveExecutor
from fedotmas.engine.store import Store
from fedotmas.engine.terminate import Goal


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
