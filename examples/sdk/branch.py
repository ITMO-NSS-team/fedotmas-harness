import asyncio

from fedotmas.engine.contract import View
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


router = branch(classify, {"math": solve, "prose": write, "code": code})


async def run(q: str) -> None:
    print(f"q = {q!r}")
    async for r in router.stream(q):
        print(f"  step {r.step}: {r.fired} -> {[f.tag for f in r.writes]}")
    out = await router.run(q)
    assert out.ok, (out.reason, out.errors)
    print("  answer:", out.value)


async def main() -> None:
    await run("2 + 2")
    await run("what is a haiku?")
    await run("sort a list")


if __name__ == "__main__":
    asyncio.run(main())
