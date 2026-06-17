import asyncio
from collections import Counter

from fedotmas.engine.contract import Fact, View
from fedotmas.engine.executor import ReactiveExecutor
from fedotmas.engine.store import Store
from fedotmas.engine.terminate import Goal
from fedotmas.sdk import action, gather


@action
async def solver_a(q: str, view: View) -> str:
    return "42"


@action
async def solver_b(q: str, view: View) -> str:
    return "42"


@action
async def solver_c(q: str, view: View) -> str:
    return "41"


@action
async def majority(answers: list[str], view: View) -> str:
    return Counter(answers).most_common(1)[0][0]


async def main() -> None:
    vote = gather(solver_a, solver_b, solver_c) + majority
    store = Store()
    stream = ReactiveExecutor().stream(
        vote.system(entry="q", out="answer"),
        store,
        seed=[Fact(tag="q", value="the meaning?")],
        terminate=Goal(lambda v: v.exists("answer")),
    )
    print("self-consistency: gather(a, b, c) + majority")
    async for r in stream:
        print(f"  step {r.step}: {r.fired} -> {[f.tag for f in r.writes]}")
    print("  answer:", store.snapshot().value("answer"))


if __name__ == "__main__":
    asyncio.run(main())
