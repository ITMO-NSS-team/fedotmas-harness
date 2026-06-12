"""The dsl surface: parse, the error contract, compile to a runnable flow, schema export."""

import json
from typing import Any

import pytest
from pydantic import BaseModel

from fedotmas.dsl import (
    Manifest,
    ManifestError,
    compile,
    manifest_schema,
    merge,
    parse,
    schema_for_flow,
)
from fedotmas.engine import View
from fedotmas.sdk import action


class FakeLLM:
    def __init__(self, reply) -> None:
        self._reply = reply

    async def complete(
        self, prompt: str, input: Any, view: View, returns: Any = str
    ) -> Any:
        return self._reply(prompt, input)


tagger = FakeLLM(lambda prompt, input: f"{prompt}({input})")


def doc(**sections) -> str:
    return json.dumps({"version": 1, **sections})


def test_parse_validates_a_json_document():
    m = parse(doc(nodes={"a": "say a"}, flow="a"))
    assert m.nodes == {"a": "say a"}
    assert m.flow == "a"


def test_parse_rejects_invalid_json():
    with pytest.raises(ManifestError) as e:
        parse("nope{")
    assert e.value.issues[0].path == "<document>"
    assert e.value.issues[0].expected == "valid JSON"


def test_parse_rejects_a_non_object():
    with pytest.raises(ManifestError, match="object"):
        parse("[1]")


def test_parse_reports_paths_into_the_document():
    bad = doc(nodes={"a": {"prompt": "p", "labels": ["x"], "returns": "str"}}, flow="a")
    with pytest.raises(ManifestError) as e:
        parse(bad)
    assert [i.path for i in e.value.issues] == ["nodes.a"]


def test_one_defect_reports_one_document_path():
    bad = doc(nodes={"a": "A"}, flow={"loop": {"gather": ["a", 5]}, "until": "done"})
    with pytest.raises(ManifestError) as e:
        parse(bad)
    assert [i.path for i in e.value.issues] == ["flow.loop.gather.1"]
    assert "not a flow expression" in e.value.issues[0].message


def test_inline_field_names_are_validated():
    for bad in ("_x", "model_config", "no spaces"):
        with pytest.raises(ManifestError) as e:
            parse(doc(nodes={"j": {"prompt": "p", "returns": {bad: "str"}}}, flow="j"))
        assert e.value.issues[0].path.startswith("nodes.j.returns")


def test_nodes_and_flows_share_one_namespace():
    with pytest.raises(ManifestError, match="namespace"):
        parse(doc(nodes={"x": "p"}, flows={"x": ["x"]}, flow="x"))


def test_step_takes_exactly_one_of_into_or_merge():
    with pytest.raises(ManifestError, match="exactly one"):
        parse(doc(nodes={"a": "p"}, flow={"step": "a"}))
    with pytest.raises(ManifestError, match="exactly one"):
        parse(doc(nodes={"a": "p"}, flow={"step": "a", "into": "k", "merge": True}))


async def test_compile_runs_a_sequence():
    m = parse(doc(nodes={"a": "A", "b": "B"}, flow=["a", "b"]))
    run = await compile(m).run("x", llm=tagger)
    assert run.ok
    assert run.value == "B(A(x))"


async def test_compile_gathers_in_branch_order():
    m = parse(doc(nodes={"a": "A", "b": "B"}, flow={"gather": ["a", "b"]}))
    run = await compile(m).run("x", llm=tagger)
    assert run.value == ["A(x)", "B(x)"]


async def test_compile_branch_routes_by_state_key():
    m = parse(
        doc(
            nodes={"a": "A", "b": "B"},
            flow={"branch": "route", "cases": {"left": "a", "right": "b"}},
        )
    )
    run = await compile(m).run({"route": "right"}, llm=tagger)
    assert run.value == "B({'route': 'right'})"


async def test_compile_loop_until_condition_over_state():
    async def bump(s, view):
        return {**s, "n": s["n"] + 1}

    m = parse(
        doc(
            nodes={"bump": {"ref": "bump"}},
            flow={"loop": "bump", "until": {"key": "n", "op": "gte", "value": 2}},
        )
    )
    run = await compile(m, atoms={"bump": action(bump)}).run({"n": 0})
    assert run.value == {"n": 2}


async def test_compile_loop_until_bare_key():
    async def finish(s, view):
        return {**s, "done": True}

    m = parse(
        doc(
            nodes={"finish": {"ref": "finish"}},
            flow={"loop": "finish", "until": "done"},
        )
    )
    run = await compile(m, atoms={"finish": action(finish)}).run({"done": False})
    assert run.value == {"done": True}


async def test_compile_step_threads_state_into_a_key():
    m = parse(
        doc(
            nodes={"note": {"prompt": "N", "takes": "dict"}},
            flow={"step": "note", "into": "note"},
        )
    )
    run = await compile(m).run({"q": "hi"}, llm=tagger)
    assert run.value == {"q": "hi", "note": "N({'q': 'hi'})"}


async def test_compile_step_merges_a_structured_reply():
    m = parse(
        doc(
            nodes={
                "judge": {
                    "prompt": "J",
                    "takes": "dict",
                    "returns": {"approved": "bool"},
                }
            },
            flow={"step": "judge", "merge": True},
        )
    )
    run = await compile(m).run({"q": 1}, llm=FakeLLM(lambda p, i: {"approved": True}))
    assert run.value == {"q": 1, "approved": True}


async def test_inline_list_fields_type_the_reply():
    m = parse(
        doc(
            nodes={"p": {"prompt": "P", "returns": {"items": ["str"], "n": "int"}}},
            flow="p",
        )
    )

    class StructuredLLM:
        async def complete(
            self, prompt: str, input: Any, view: View, returns: Any = str
        ) -> Any:
            return returns(items=["a", "b"], n=2)

    run = await compile(m).run("x", llm=StructuredLLM())
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
    flow = compile(m, types={"Verdict": Verdict})
    run = await flow.run({"q": 1}, llm=FakeLLM(lambda p, i: Verdict(approved=True)))
    assert run.value == {"q": 1, "approved": True}


async def test_router_labels_drive_branch():
    m = parse(
        doc(
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
    )
    llm = FakeLLM(lambda p, i: "right" if p == "R" else f"{p}({i})")
    run = await compile(m).run({"q": 1}, llm=llm)
    assert run.value == "Q({'q': 1, 'route': 'right'})"


async def test_named_flow_splices_inline():
    m = parse(
        doc(
            nodes={"a": "A", "b": "B", "c": "C"},
            flows={"pair": ["a", "b"]},
            flow=["pair", "c"],
        )
    )
    run = await compile(m).run("x", llm=tagger)
    assert run.value == "C(B(A(x)))"


async def test_nest_runs_a_named_flow_as_one_node():
    m = parse(
        doc(
            nodes={"a": "A", "b": "B"},
            flows={"pair": ["a", "b"]},
            flow={"nest": "pair"},
        )
    )
    run = await compile(m).run("x", llm=tagger)
    assert run.value == "B(A(x))"


def test_nest_of_a_manifest_is_reserved():
    m = parse(
        doc(
            flows={"other": ["x"]},
            nodes={"x": "X"},
            flow={"nest": {"manifest": "other"}},
        )
    )
    with pytest.raises(ManifestError, match="not implemented"):
        compile(m)


def test_compile_collects_every_issue():
    m = parse(
        doc(
            nodes={"a": {"ref": "ghost"}, "b": {"prompt": "p", "returns": "Missing"}},
            flow=["a", "b", "zzz"],
        )
    )
    with pytest.raises(ManifestError) as e:
        compile(m)
    assert [i.path for i in e.value.issues] == [
        "nodes.a.ref",
        "nodes.b.returns",
        "flow.2",
    ]
    assert e.value.issues[2].expected == "one of ['a', 'b']"


def test_circular_flow_reference_is_an_error():
    m = parse(doc(flows={"x": ["y"], "y": ["x"]}, flow="x"))
    with pytest.raises(ManifestError, match="circular"):
        compile(m)


def test_compile_requires_the_flow_section():
    m = Manifest.model_validate({"version": 1, "nodes": {"a": "p"}})
    with pytest.raises(ManifestError) as e:
        compile(m)
    assert e.value.issues[0].path == "flow"


async def test_merge_overlays_a_staged_emission():
    pool = Manifest.model_validate({"version": 1, "nodes": {"a": "A", "b": "B"}})
    wiring = Manifest.model_validate({"version": 1, "flow": ["a", "b"]})
    run = await compile(merge(pool, wiring)).run("x", llm=tagger)
    assert run.value == "B(A(x))"


def test_merge_rejects_a_name_defined_twice():
    one = Manifest.model_validate({"version": 1, "nodes": {"a": "A"}})
    two = Manifest.model_validate({"version": 1, "nodes": {"a": "A2"}})
    with pytest.raises(ManifestError) as e:
        merge(one, two)
    assert e.value.issues[0].path == "nodes.a"


def test_manifest_schema_names_the_productions():
    s = manifest_schema()
    assert {"FlowExpr", "Gather", "Branch", "Loop", "Nest", "Step"} <= s["$defs"].keys()


def test_schema_for_flow_closes_names_over_the_pool():
    s = schema_for_flow(["b", "a"])
    union = s["$defs"]["FlowExpr"]["oneOf"]
    assert {"enum": ["a", "b"]} in union
    assert {"type": "string"} not in union
    assert s["$defs"]["Branch"]["properties"]["branch"]["type"] == "string"


def test_schema_for_flow_rejects_an_empty_pool():
    with pytest.raises(ValueError, match="non-empty"):
        schema_for_flow([])
