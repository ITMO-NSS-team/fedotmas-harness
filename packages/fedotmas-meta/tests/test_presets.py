"""The presets surface: fill checks and assemble building a runnable flow from a SystemSpec,
over caller-supplied presets. The fixtures here are minimal on purpose — they exercise the
mechanism (a single role, a many role + reserved wiring), not any shipped topology."""

from typing import Any

import pytest
from fedotmas import Flow, gather
from fedotmas.engine import View
from fedotmas_llm import Call, agent
from fedotmas_meta import (
    AgentSpec,
    ResolvedFill,
    RoleSpec,
    SystemSpec,
    assemble,
    group,
    solo,
)


class FakeLLM:
    def __init__(self, reply) -> None:
        self._reply = reply

    async def complete(self, call: Call, view: View) -> Any:
        return self._reply(call.prompt, call.input)


tagger = FakeLLM(lambda p, i: f"{p}({i})")


class Solo:
    """One role -> one agent: the smallest preset that assembles to a runnable flow."""

    name = "solo"
    hint = "one speaker answers the question"
    roles = (RoleSpec("speaker", "answers"),)
    reserved = frozenset[str]()

    def build(self, fill: ResolvedFill) -> Flow:
        b = solo(fill["speaker"])
        return agent("speaker", prompt=b.prompt, llm=b.llm, tools=list(b.tools) or None)


class Panel:
    """A many role plus a single judge: exercises the dict-of-AgentSpec shape and reserved
    wiring names."""

    name = "panel"
    hint = "voters answer in parallel, a judge decides"
    roles = (RoleSpec("voters", "debaters", many=True), RoleSpec("judge", "decides"))
    reserved = frozenset({"judge"})

    def build(self, fill: ResolvedFill) -> Flow:
        voters = group(fill["voters"])
        judge = solo(fill["judge"])
        panel = gather(
            *(agent(n, prompt=b.prompt, llm=b.llm) for n, b in voters.items())
        )
        decide = agent(
            "judge", prompt=judge.prompt, takes=list[str], returns=str, llm=judge.llm
        )
        return panel + decide


CATALOG = (Solo(), Panel())


def test_unknown_preset_lists_the_menu():
    spec = SystemSpec(preset="nope", fill={})
    with pytest.raises(KeyError, match="solo"):
        assemble(spec, presets=CATALOG)


def test_missing_role_is_rejected():
    spec = SystemSpec(preset="solo", fill={})
    with pytest.raises(ValueError, match="missing"):
        assemble(spec, presets=CATALOG)


def test_many_role_name_cannot_clash_with_wiring():
    spec = SystemSpec(
        preset="panel",
        fill={
            "voters": {"judge": AgentSpec(prompt="v")},
            "judge": AgentSpec(prompt="j"),
        },
    )
    with pytest.raises(ValueError, match="reserved"):
        assemble(spec, presets=CATALOG)


def test_unknown_model_is_named():
    spec = SystemSpec(
        preset="solo", fill={"speaker": AgentSpec(prompt="s", model="ghost")}
    )
    with pytest.raises(KeyError, match="ghost"):
        assemble(spec, presets=CATALOG, models={})


async def test_solo_settles_to_an_answer():
    spec = SystemSpec(preset="solo", fill={"speaker": AgentSpec(prompt="S")})
    flow = assemble(spec, presets=CATALOG)
    run = await flow.run("q", bind={"llm": tagger})
    assert run.ok
    assert run.value == "S(q)"


async def test_panel_settles_to_a_verdict():
    spec = SystemSpec(
        preset="panel",
        fill={
            "voters": {"yes": AgentSpec(prompt="Y"), "no": AgentSpec(prompt="N")},
            "judge": AgentSpec(prompt="J"),
        },
    )
    flow = assemble(spec, presets=CATALOG)
    run = await flow.run("q", bind={"llm": tagger})
    assert run.ok
    assert run.value.startswith("J(")
