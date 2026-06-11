"""TDD spec for the stateful surface: templates, into/merge, key-driven loop and branch, run.

This pins the declarative state machinery: an agent node picks what the model sees with an
`input` template over the state, puts the reply back with `into` (one key) or `merge`
(structured reply folded into the state), a branch routes by a state key, a loop stops on a
state key, and Flow.run executes the whole thing with the llm bound once as the default.
A failing node ends the run with reason "error" instead of a traceback. The asserts are the
contract; a FakeLLM stands in for the backend so the spec runs offline.
"""

import asyncio
from typing import Any

from pydantic import BaseModel

from fedotmas.engine.contract import View
from fedotmas.sdk import agent, branch


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
    # into=: template picks from the state, the reply lands under one key.
    note = agent(
        "note",
        prompt="Restate the ticket in one line.",
        input="Ticket: {ticket}",
        into="summary",
    )
    run = await note.run(
        {"ticket": "double charge"},
        llm=FakeLLM(lambda p, content: f"noted({content})"),
    )
    assert run.ok and run.reason == "goal", (run.reason, run.errors)
    assert run.value == {
        "ticket": "double charge",
        "summary": "noted(Ticket: double charge)",
    }, run.value
    print("into + template:", run.value)

    # merge= + branch by state key + loop until state key: a two-hop handoff.
    hop = agent(
        "hop",
        prompt="Handle and hand off.",
        input="{ticket}",
        returns=Patch,
        merge=True,
    )
    handle = branch("station", {"triage": hop, "tech": hop})
    flow = handle.loop(until="done")
    hops = iter([Patch(station="tech", done=False), Patch(station="tech", done=True)])
    run = await flow.run(
        {"ticket": "app crash after charge fix", "station": "triage"},
        llm=FakeLLM(lambda p, content: next(hops)),
        budget=8,
    )
    assert run.ok and run.value["done"] and run.value["station"] == "tech", run.value
    print("merge + branch('station') + loop('done'):", run.value)

    # a failing node ends the run as an error outcome, not a traceback
    bad = agent("bad", prompt="x", input="{missing_key}", takes=dict, returns=str)
    run = await bad.run({"ticket": "x"}, llm=FakeLLM(lambda p, c: c))
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
