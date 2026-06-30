"""The agent atom: templated input, structured and label outputs, llm binding."""

from typing import Any

import pytest
from fedotmas import branch
from fedotmas.engine import View
from fedotmas_llm import agent
from pydantic import BaseModel


class FakeLLM:
    def __init__(self, reply) -> None:
        self._reply = reply

    async def complete(
        self, prompt: str, input: Any, view: View, returns: Any = str, tools: Any = None
    ) -> Any:
        return self._reply(prompt, input)


class Patch(BaseModel):
    station: str
    done: bool


async def test_into_threads_state_through_a_template():
    note = agent(
        "note",
        prompt="Restate the ticket.",
        input="Ticket: {ticket}",
        takes=dict,
        returns=str,
    ).into("summary")
    run = await note.run(
        {"ticket": "double charge"},
        bind={"llm": FakeLLM(lambda p, content: f"noted({content})")},
    )
    assert run.ok
    assert run.value == {
        "ticket": "double charge",
        "summary": "noted(Ticket: double charge)",
    }


async def test_merge_branch_loop_make_a_handoff():
    hop = agent(
        "hop",
        prompt="Handle and hand off.",
        input="{ticket}",
        takes=dict,
        returns=Patch,
    ).merge()
    flow = branch("station", {"triage": hop, "tech": hop}).loop(until="done")
    hops = iter([Patch(station="tech", done=False), Patch(station="tech", done=True)])
    run = await flow.run(
        {"ticket": "app crash", "station": "triage"},
        bind={"llm": FakeLLM(lambda p, content: next(hops))},
        budget=8,
    )
    assert run.ok
    assert run.value["done"] and run.value["station"] == "tech"


async def test_a_failing_node_is_an_error_outcome():
    bad = agent("bad", prompt="x", input="{missing_key}", takes=dict, returns=str)
    run = await bad.run({"ticket": "x"}, bind={"llm": FakeLLM(lambda p, c: c)})
    assert not run.ok
    assert run.reason == "error"
    assert run.errors[0].producer.startswith("bad")


def test_an_unbound_llm_fails_at_compile_time():
    with pytest.raises(ValueError, match="no llm bound"):
        agent("loose", prompt="x").system(entry="in", out="out")


async def test_a_per_node_llm_overrides_the_run_default():
    pinned = agent("pinned", prompt="p", llm=FakeLLM(lambda p, c: "node"))
    run = await pinned.run("q", bind={"llm": FakeLLM(lambda p, c: "run")})
    assert run.value == "node"


async def test_labels_make_a_validated_classifier():
    pick = agent("pick", prompt="route", labels=["a", "b"])
    run = await pick.run("q", bind={"llm": FakeLLM(lambda p, c: "a")})
    assert run.value == "a"
    run = await pick.run("q", bind={"llm": FakeLLM(lambda p, c: "zzz")})
    assert not run.ok
    assert "not in" in run.errors[0].value


def test_labels_do_not_combine_with_returns():
    with pytest.raises(ValueError, match="does not combine with returns="):
        agent("x", prompt="p", labels=["a"], returns=int)  # type: ignore
