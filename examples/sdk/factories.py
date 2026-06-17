import asyncio
from typing import Any

from fedotmas.engine.contract import Fact, View
from fedotmas.engine.executor import ReactiveExecutor
from fedotmas.engine.store import Store
from fedotmas.engine.terminate import Goal
from fedotmas.sdk import action, agent, branch


class FakeLLM:
    def __init__(self, reply) -> None:
        self._reply = reply

    async def complete(
        self, prompt: str, input: Any, view: View, returns: type = str
    ) -> Any:
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
        llm=FakeLLM(lambda prompt, text: text.split()[0]),
    )
    chain = shout + summarize
    result = await run(
        "chain: shout + summarize (action + agent)",
        chain.system(entry="text", out="out"),
        Fact(tag="text", value="hello world"),
        "out",
    )
    assert result == "HELLO", result

    route = agent(
        "route",
        prompt="Pick the topic:",
        labels=["math", "prose"],
        llm=FakeLLM(lambda prompt, q: "math" if q[0].isdigit() else "prose"),
    )
    solver = agent("solve", prompt="Solve:", llm=FakeLLM(lambda p, q: f"{q} = 4"))
    writer = agent("write", prompt="Write:", llm=FakeLLM(lambda p, q: f"prose: {q}"))
    router = branch(route, {"math": solver, "prose": writer})
    answer = await run(
        "branch: agent(labels=...) -> {math: solve, prose: write}",
        router.system(entry="q", out="answer"),
        Fact(tag="q", value="2 + 2"),
        "answer",
    )
    assert answer == "2 + 2 = 4", answer

    print("OK")


if __name__ == "__main__":
    asyncio.run(main())
