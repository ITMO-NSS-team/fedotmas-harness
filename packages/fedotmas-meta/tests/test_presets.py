"""The presets surface: catalog, fill checks, and the blackboard preset building a flow. The
flow presets are temporarily out during the dsl refactor (see commit 2bd05ed)."""

from typing import Any

import pytest
from fedotmas.engine import View
from fedotmas_meta.presets import catalog, get


class FakeLLM:
    def __init__(self, reply) -> None:
        self._reply = reply

    async def complete(
        self, prompt: str, input: Any, view: View, returns: Any = str
    ) -> Any:
        return self._reply(prompt, input)


tagger = FakeLLM(lambda p, i: f"{p}({i})")


def test_catalog_is_the_closed_menu():
    assert [p.name for p in catalog()] == ["blackboard"]
    assert all(p.hint and p.roles for p in catalog())


def test_get_unknown_name_lists_the_menu():
    with pytest.raises(KeyError, match="blackboard"):
        get("nope")


def test_fill_is_checked():
    with pytest.raises(ValueError, match="missing"):
        get("blackboard").build({"researcher": "r"})
    with pytest.raises(ValueError, match="prompt string"):
        get("blackboard").build({"researcher": "r", "skeptic": "k", "synthesizer": ""})


async def test_blackboard_settles_to_an_answer():
    flow = get("blackboard").build(
        {"researcher": "F", "skeptic": "K", "synthesizer": "Z"}
    )
    run = await flow.run("q", bind={"llm": tagger})
    assert run.ok
    assert run.value.startswith("Z(")
    assert "F(q)" in run.value
