import asyncio
from typing import Any

from fedotmas import branch
from fedotmas.engine.contract import View
from fedotmas_llm import agent
from pydantic import BaseModel


class FakeLLM:
    def __init__(self, reply) -> None:
        self._reply = reply

    async def complete(
        self, prompt: str, input: Any, view: View, returns: Any = str
    ) -> Any:
        return self._reply(prompt, input)


class Patch(BaseModel):
    station: str
    done: bool


async def main() -> None:
    # .into(): template picks from the state, the reply lands under one key.
    note = agent(
        "note",
        prompt="Restate the ticket in one line.",
        input="Ticket: {ticket}",
        takes=dict,
        returns=str,
    ).into("summary")
    run = await note.run(
        {"ticket": "double charge"},
        bind={"llm": FakeLLM(lambda p, content: f"noted({content})")},
    )
    # .unwrap() returns the value or raises RunError; the escalation when a failed run
    # should be an exception rather than a None to branch on.
    value = run.unwrap()
    assert value == {
        "ticket": "double charge",
        "summary": "noted(Ticket: double charge)",
    }, value
    print(".into + template:", value)

    # .merge() + branch by state key + loop until state key: a two-hop handoff.
    hop = agent(
        "hop",
        prompt="Handle and hand off.",
        input="{ticket}",
        takes=dict,
        returns=Patch,
    ).merge()
    handle = branch("station", {"triage": hop, "tech": hop})
    flow = handle.loop(until="done")
    hops = iter([Patch(station="tech", done=False), Patch(station="tech", done=True)])
    run = await flow.run(
        {"ticket": "app crash after charge fix", "station": "triage"},
        bind={"llm": FakeLLM(lambda p, content: next(hops))},
        budget=8,
    )
    assert run.ok and run.value["done"] and run.value["station"] == "tech", run.value
    print(".merge + branch('station') + loop('done'):", run.value)

    # a failing node ends the run as an error outcome, not a traceback
    bad = agent("bad", prompt="x", input="{missing_key}", takes=dict, returns=str)
    run = await bad.run({"ticket": "x"}, bind={"llm": FakeLLM(lambda p, c: c)})
    assert not run.ok and run.reason == "error", run.reason
    assert run.errors and run.errors[0].producer.startswith("bad"), run.errors
    print("error outcome:", run.errors[0].value)

    # an unbound llm fails at compile time, before anything runs
    try:
        agent("loose", prompt="x").system(entry="in", out="out")
    except ValueError as e:
        print("unbound llm:", e)
    else:
        raise AssertionError("expected compile-time failure for unbound llm")

    print("OK")


if __name__ == "__main__":
    asyncio.run(main())
