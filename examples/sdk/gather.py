import asyncio
from collections import Counter

from fedotmas.engine.contract import View
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
    print("self-consistency: gather(a, b, c) + majority")
    async for r in vote.stream("the meaning?"):
        print(f"  step {r.step}: {r.fired} -> {[f.tag for f in r.writes]}")
    run = await vote.run("the meaning?")
    assert run.ok and run.value == "42", (run.reason, run.value)
    print("  answer:", run.value)


if __name__ == "__main__":
    asyncio.run(main())
