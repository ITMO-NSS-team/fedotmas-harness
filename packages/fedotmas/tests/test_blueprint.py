"""to_blueprint: a compiled System projected to its declarative shape, before any run. The
cross-check asserts the declared writes/edges cover what a run actually produces (to_graph)."""

from _helpers import (
    bump,
    count,
    double,
    gate,
    has_edge,
    node,
    pick_a,
    pick_b,
    run_flow,
    score,
    triple,
    upper,
)
from fedotmas import Rule, action, blackboard, branch, gather, nest
from fedotmas.serialize import Blueprint, to_blueprint, to_graph
from fedotmas.serialize._dataflow import _matches


def _covers(declared, observed):
    return all(any(_matches(o, d) for d in declared) for o in observed)


def test_seq_is_compile_time():
    bp = to_blueprint((action(double) + action(triple)).system(entry="in", out="out"))
    assert node(bp, "double#1").kind == "action"
    assert node(bp, "double#1").writes == ["double#1"]
    assert has_edge(bp, "double#1", "triple#2")
    assert has_edge(bp, "triple#2", "alias:out")


def test_gather_params():
    bp = to_blueprint(
        gather(action(double), action(triple)).system(entry="in", out="out")
    )
    assert node(bp, "gather#1").kind == "gather"
    assert set(node(bp, "gather#1").params["srcs"]) == {"double#2", "triple#3"}
    assert has_edge(bp, "double#2", "gather#1")


def test_branch_select_spec_survives():
    bp = to_blueprint(
        branch("kind", {"x": action(pick_a), "y": action(pick_b)}).system(
            entry="in", out="out"
        )
    )
    route = node(bp, "branch#1:route")
    assert route.kind == "branch.route"
    assert route.params["select"] == {"by": "state", "key": "kind"}
    assert set(route.params["cases"]) == {"x", "y"}
    assert set(route.writes) == {"branch#1:in:x", "branch#1:in:y"}
    assert node(bp, "branch#1:join:y").kind == "branch.join"


def test_loop_until_spec_and_body_recurse():
    bp = to_blueprint(action(bump).loop(until="done").system(entry="in", out="out"))
    it = node(bp, "loop#1:iter")
    assert it.kind == "loop.iter"
    assert it.params["until"] == {"key": "done"}
    assert it.inner is not None
    assert any(n.kind == "action" for n in it.inner.nodes)
    assert node(bp, "loop#1:done").kind == "loop.done"


def test_board_uniform_with_flow():
    board = blackboard(
        Rule("score", score, reads="draft", writes="score"),
        Rule("gate", gate, reads="score", writes="verdict", when=["score", "!verdict"]),
    )
    bp = to_blueprint(board.compile())
    assert node(bp, "score").kind == "rule"
    assert node(bp, "score").writes == ["score"]
    assert node(bp, "gate").writes == ["verdict"]
    assert node(bp, "gate").params["when"] == {
        "all": [
            {"key": "score", "op": "exists"},
            {"not": {"key": "verdict", "op": "exists"}},
        ]
    }
    assert has_edge(bp, "score", "gate")


def test_flow_over_board_recurses():
    inner = blackboard(Rule("count", count, reads="topic", writes="report"))
    flow = action(upper) + nest(inner, entry="topic", out="report")
    bp = to_blueprint(flow.system(entry="in", out="out"))
    nestnode = node(bp, "nest#2")
    assert nestnode.kind == "nest"
    assert nestnode.params["entry"] == "topic"
    assert nestnode.params["out"] == "report"
    assert "system" not in nestnode.params
    assert nestnode.inner is not None
    assert node(nestnode.inner, "count").kind == "rule"
    assert has_edge(bp, "upper#1", "nest#2")


def test_blueprint_is_json_clean():
    inner = blackboard(Rule("count", count, reads="topic", writes="report"))
    flow = action(upper) + nest(inner, entry="topic", out="report")
    bp = to_blueprint(flow.system(entry="in", out="out"))
    again = Blueprint.model_validate_json(bp.model_dump_json())
    assert node(again, "nest#2").inner is not None


async def test_declared_covers_observed():
    cases = [
        (action(double) + action(triple), 2),
        (gather(action(double), action(triple)), 3),
        (branch("kind", {"x": action(pick_a), "y": action(pick_b)}), {"kind": "y"}),
        (action(bump).loop(until="done"), {"n": 0, "done": False}),
    ]
    for flow, value in cases:
        system, run = await run_flow(flow, value)
        bp = to_blueprint(system)
        g = to_graph(system, run)
        declared = {n.name: n.writes for n in bp.nodes}
        for gn in g.nodes:
            assert _covers(declared[gn.name], gn.writes), (gn.name, gn.writes)
        bp_edges = {(e.src, e.dst) for e in bp.edges}
        for ge in g.edges:
            assert (ge.src, ge.dst) in bp_edges, (ge.src, ge.dst)
