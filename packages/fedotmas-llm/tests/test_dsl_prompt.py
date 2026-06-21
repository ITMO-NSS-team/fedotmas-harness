"""DSL prompt nodes: a bare string or a prompt object compiles via the agent provider."""

import json
from typing import Any

import pytest
from fedotmas.dsl import ManifestError, compile, parse
from fedotmas.engine import View
from fedotmas_llm import agent
from pydantic import BaseModel


class FakeLLM:
    def __init__(self, reply) -> None:
        self._reply = reply

    async def complete(
        self, prompt: str, input: Any, view: View, returns: Any = str
    ) -> Any:
        return self._reply(prompt, input)


tagger = FakeLLM(lambda prompt, input: f"{prompt}({input})")
AGENTS = {"agent": agent}


def doc(**sections) -> str:
    return json.dumps({"version": 1, **sections})


def build(**sections):
    return compile(parse(doc(**sections)), providers=AGENTS)


async def test_compile_runs_a_sequence():
    flow = build(nodes={"a": "A", "b": "B"}, flow=["a", "b"])
    run = await flow.run("x", bind={"llm": tagger})
    assert run.ok
    assert run.value == "B(A(x))"


async def test_compile_gathers_in_branch_order():
    flow = build(nodes={"a": "A", "b": "B"}, flow={"gather": ["a", "b"]})
    run = await flow.run("x", bind={"llm": tagger})
    assert run.value == ["A(x)", "B(x)"]


async def test_compile_branch_routes_by_state_key():
    flow = build(
        nodes={"a": "A", "b": "B"},
        flow={"branch": "route", "cases": {"left": "a", "right": "b"}},
    )
    run = await flow.run({"route": "right"}, bind={"llm": tagger})
    assert run.value == "B({'route': 'right'})"


async def test_compile_step_threads_state_into_a_key():
    flow = build(
        nodes={"note": {"prompt": "N", "takes": "dict"}},
        flow={"step": "note", "into": "note"},
    )
    run = await flow.run({"q": "hi"}, bind={"llm": tagger})
    assert run.value == {"q": "hi", "note": "N({'q': 'hi'})"}


async def test_compile_step_merges_a_structured_reply():
    flow = build(
        nodes={
            "judge": {"prompt": "J", "takes": "dict", "returns": {"approved": "bool"}}
        },
        flow={"step": "judge", "merge": True},
    )
    run = await flow.run(
        {"q": 1}, bind={"llm": FakeLLM(lambda p, i: {"approved": True})}
    )
    assert run.value == {"q": 1, "approved": True}


async def test_inline_list_fields_type_the_reply():
    flow = build(
        nodes={"p": {"prompt": "P", "returns": {"items": ["str"], "n": "int"}}},
        flow="p",
    )

    class StructuredLLM:
        async def complete(
            self, prompt: str, input: Any, view: View, returns: Any = str
        ) -> Any:
            return returns(items=["a", "b"], n=2)

    run = await flow.run("x", bind={"llm": StructuredLLM()})
    assert run.value.items == ["a", "b"]
    assert run.value.n == 2


async def test_returns_resolves_from_the_types_registry():
    class Verdict(BaseModel):
        approved: bool

    m = parse(
        doc(
            nodes={"judge": {"prompt": "J", "takes": "dict", "returns": "Verdict"}},
            flow={"step": "judge", "merge": True},
        )
    )
    flow = compile(m, types={"Verdict": Verdict}, providers=AGENTS)
    run = await flow.run(
        {"q": 1}, bind={"llm": FakeLLM(lambda p, i: Verdict(approved=True))}
    )
    assert run.value == {"q": 1, "approved": True}


async def test_router_labels_drive_branch():
    flow = build(
        nodes={
            "router": {"prompt": "R", "takes": "dict", "labels": ["left", "right"]},
            "l": {"prompt": "L", "takes": "dict"},
            "r": {"prompt": "Q", "takes": "dict"},
        },
        flow=[
            {"step": "router", "into": "route"},
            {"branch": "route", "cases": {"left": "l", "right": "r"}},
        ],
    )
    llm = FakeLLM(lambda p, i: "right" if p == "R" else f"{p}({i})")
    run = await flow.run({"q": 1}, bind={"llm": llm})
    assert run.value == "Q({'q': 1, 'route': 'right'})"


async def test_named_flow_splices_inline():
    flow = build(
        nodes={"a": "A", "b": "B", "c": "C"},
        flows={"pair": ["a", "b"]},
        flow=["pair", "c"],
    )
    run = await flow.run("x", bind={"llm": tagger})
    assert run.value == "C(B(A(x)))"


async def test_nest_runs_a_named_flow_as_one_node():
    flow = build(
        nodes={"a": "A", "b": "B"},
        flows={"pair": ["a", "b"]},
        flow={"nest": "pair"},
    )
    run = await flow.run("x", bind={"llm": tagger})
    assert run.value == "B(A(x))"


def test_a_prompt_node_without_a_provider_fails():
    m = parse(doc(nodes={"a": "A"}, flow="a"))
    with pytest.raises(ManifestError, match="agent"):
        compile(m)
