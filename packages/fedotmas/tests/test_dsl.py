"""The dsl surface: parse, the error contract, compile to a runnable flow, schema export.

Prompt-node compilation (a bare string or a prompt object needs the agent provider) lives in
the fedotmas-llm test suite; here every compile uses code atoms by ref, so no provider binds.
"""

import json

import pytest
from fedotmas import action
from fedotmas.dsl import (
    Manifest,
    ManifestError,
    compile,
    manifest_schema,
    merge,
    parse,
    schema_for_flow,
)


def doc(**sections) -> str:
    return json.dumps({"version": 1, **sections})


async def echo(value, view):
    return value


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


async def test_merge_overlays_a_staged_emission():
    pool = Manifest.model_validate(
        {"version": 1, "nodes": {"a": {"ref": "a"}, "b": {"ref": "b"}}}
    )
    wiring = Manifest.model_validate({"version": 1, "flow": ["a", "b"]})
    flow = compile(merge(pool, wiring), atoms={"a": action(echo), "b": action(echo)})
    assert (await flow.run("x")).value == "x"


def test_nest_of_a_manifest_is_reserved():
    m = parse(
        doc(
            flows={"other": ["x"]},
            nodes={"x": {"ref": "x"}},
            flow={"nest": {"manifest": "other"}},
        )
    )
    with pytest.raises(ManifestError, match="not implemented"):
        compile(m, atoms={"x": action(echo)})


def test_compile_collects_every_issue():
    m = parse(
        doc(
            nodes={"a": {"ref": "ghost"}, "b": {"ref": "phantom"}},
            flow=["a", "b", "zzz"],
        )
    )
    with pytest.raises(ManifestError) as e:
        compile(m)
    assert [i.path for i in e.value.issues] == ["nodes.a.ref", "nodes.b.ref", "flow.2"]
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
