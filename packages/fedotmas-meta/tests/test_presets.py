"""The presets surface: catalog, fill checks, both backings build runnable flows."""

from typing import Any

import pytest
from fedotmas import dsl
from fedotmas.engine import View
from fedotmas_llm import agent
from fedotmas_meta.presets import DataPreset, catalog, get


class FakeLLM:
    def __init__(self, reply) -> None:
        self._reply = reply

    async def complete(
        self, prompt: str, input: Any, view: View, returns: Any = str
    ) -> Any:
        return self._reply(prompt, input)


tagger = FakeLLM(lambda p, i: f"{p}({i})")


def test_catalog_is_the_closed_menu():
    assert [p.name for p in catalog()] == [
        "single",
        "chain",
        "debate",
        "eval_optimizer",
        "orchestrator",
        "router",
        "blackboard",
    ]
    assert all(p.hint and p.roles for p in catalog())


def test_get_unknown_name_lists_the_menu():
    with pytest.raises(KeyError, match="single"):
        get("nope")


def test_fill_is_checked():
    with pytest.raises(ValueError, match="missing"):
        get("debate").build({"pro": "p"})
    with pytest.raises(ValueError, match="dict"):
        get("chain").build({"steps": "not a dict"})
    with pytest.raises(ValueError, match="reserved"):
        get("router").build({"handlers": {"dispatch": "x"}})


def test_data_presets_expose_the_manifest_and_code_presets_do_not():
    debate = get("debate")
    assert isinstance(debate, DataPreset)
    m = debate.manifest({"pro": "P", "con": "C", "judge": "J"})
    assert isinstance(m, dsl.Manifest)
    assert not isinstance(get("blackboard"), DataPreset)


async def test_single_runs():
    run = await get("single").build({"agent": "A"}).run("x", bind={"llm": tagger})
    assert run.value == "A(x)"


async def test_chain_orders_steps():
    flow = get("chain").build({"steps": {"a": "A", "b": "B"}})
    run = await flow.run("x", bind={"llm": tagger})
    assert run.value == "B(A(x))"


async def test_debate_gathers_then_judges():
    flow = get("debate").build({"pro": "P", "con": "C", "judge": "J"})
    run = await flow.run("x", bind={"llm": tagger})
    assert run.value == "J(['P(x)', 'C(x)'])"


async def test_eval_optimizer_loops_until_approved():
    drafts = iter(["one", "two"])

    def reply(p, i):
        if p == "G":
            return next(drafts)
        return "approve" if "two" in i else "revise"

    flow = get("eval_optimizer").build({"generator": "G", "critic": "C"})
    run = await flow.run("x", bind={"llm": FakeLLM(reply)})
    assert run.value == "two"


async def test_router_dispatches_to_a_handler():
    llm = FakeLLM(lambda p, i: "tech" if p.startswith("Route") else f"{p}({i})")
    flow = get("router").build({"handlers": {"billing": "B", "tech": "T"}})
    run = await flow.run("it crashed", bind={"llm": llm})
    assert run.value == "T(it crashed)"


async def test_orchestrator_loops_workers_then_synthesizes():
    picks = iter(["research", "done"])

    def reply(p, i):
        if p.startswith("You coordinate"):
            return next(picks)
        return f"{p}({i})"

    flow = get("orchestrator").build({"workers": {"research": "R"}, "synthesizer": "S"})
    run = await flow.run("x", bind={"llm": FakeLLM(reply)})
    assert run.ok
    assert run.value.startswith("S(")
    assert "R(" in run.value


async def test_blackboard_settles_to_an_answer():
    flow = get("blackboard").build(
        {"researcher": "F", "skeptic": "K", "synthesizer": "Z"}
    )
    run = await flow.run("q", bind={"llm": tagger})
    assert run.ok
    assert run.value.startswith("Z(")
    assert "F(q)" in run.value


async def test_built_preset_enters_a_manifest_by_ref():
    review = get("single").build({"agent": "R"})
    m = dsl.parse(
        '{"version": 1, "nodes": {"draft": "D", "review": {"ref": "review"}},'
        ' "flow": ["draft", "review"]}'
    )
    run = await dsl.compile(
        m, atoms={"review": review}, providers={"agent": agent}
    ).run("x", bind={"llm": tagger})
    assert run.value == "R(D(x))"
