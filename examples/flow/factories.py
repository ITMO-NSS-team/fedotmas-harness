"""TDD spec for the atom factories: action, agent, decision.

This pins the API the factory code is written against. action lifts a python function,
agent lifts a prompt into an LLM node, decision lifts a prompt into a router over a finite
label set. All three produce Flow[A, B] and compose with the same operators. The LLM seam
is the Model protocol, faked here so the spec runs without a backend.

Run after the factories exist; until then it fails on import. The asserts are the contract.
"""

import asyncio
from typing import Any

from fedotmas.sdk import action, agent, branch, decision
from fedotmas.engine.contract import Fact, View
from fedotmas.engine.executor import ReactiveExecutor
from fedotmas.engine.store import Store
from fedotmas.engine.terminate import Goal


class FakeModel:
    def __init__(self, reply) -> None:
        self._reply = reply

    async def complete(self, prompt: str, input: Any, view: View) -> Any:
        return self._reply(prompt, input)


@action
async def shout(text: str, view: View) -> str:
    return text.upper()


async def run(name: str, system, seed: Fact, out: str) -> Any:
    store = Store()
    print(name)
    async for r in ReactiveExecutor().stream(
        system, store, seed=[seed], terminate=Goal(lambda v: v.exists(out))
    ):
        print(f"  step {r.step}: {r.fired} -> {[f.tag for f in r.writes]}")
    value = store.snapshot().value(out)
    print(f"  {out}: {value}")
    return value


async def main() -> None:
    summarize = agent(
        "summarize",
        prompt="Summarize in one word:",
        model=FakeModel(lambda prompt, text: text.split()[0]),
    )
    chain = shout + summarize
    result = await run(
        "chain: shout + summarize (action + agent)",
        chain.system(entry="text", out="out"),
        Fact(tag="text", value="hello world"),
        "out",
    )
    assert result == "HELLO", result

    route = decision(
        "route",
        prompt="Pick the topic:",
        labels=["math", "prose"],
        model=FakeModel(lambda prompt, q: "math" if q[0].isdigit() else "prose"),
    )
    solver = agent("solve", prompt="Solve:", model=FakeModel(lambda p, q: f"{q} = 4"))
    writer = agent(
        "write", prompt="Write:", model=FakeModel(lambda p, q: f"prose: {q}")
    )
    router = branch(route, {"math": solver, "prose": writer})
    answer = await run(
        "branch: decision(route) -> {math: solve, prose: write}",
        router.system(entry="q", out="answer"),
        Fact(tag="q", value="2 + 2"),
        "answer",
    )
    assert answer == "2 + 2 = 4", answer

    print("OK")


if __name__ == "__main__":
    asyncio.run(main())
