"""branch: a select step writes a label, exactly one case fires on it.

Same shape as the hand-written engine/router.py. The combinator owns the label tag and
the per-case triggers. Each case receives the original entry value as its input.
"""

import asyncio

from fedotmas.dsl.combinators import branch
from fedotmas.engine.contract import Fact, View
from fedotmas.engine.executor import ReactiveExecutor
from fedotmas.engine.store import Store
from fedotmas.engine.terminate import Goal


async def classify(question: str, view: View) -> str:
    if any(c.isdigit() for c in question):
        return "math"
    if question.endswith("?"):
        return "prose"
    return "code"


async def solver(question: str, view: View) -> str:
    return f"math: {question} = 4"


async def writer(question: str, view: View) -> str:
    return f"prose answer to: {question}"


async def coder(question: str, view: View) -> str:
    return f"code for: {question}"


async def main() -> None:
    system = branch(
        classify,
        cases={"math": solver, "prose": writer, "code": coder},
        entry="q",
        out="answer",
    )
    store = Store()
    stream = ReactiveExecutor().stream(
        system,
        store,
        seed=[Fact(tag="q", value="2 + 2")],
        terminate=Goal(lambda v: v.exists("answer")),
    )
    async for r in stream:
        print(f"step {r.step}: {r.fired} -> {[f.tag for f in r.writes]}")
    print("answer:", store.snapshot().value("answer"))


if __name__ == "__main__":
    asyncio.run(main())
