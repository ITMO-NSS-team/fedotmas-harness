"""to_graph: a finished run projected to its dataflow graph, surface-agnostic over the floor."""

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
from fedotmas.engine.contract import Fact
from fedotmas.engine.executor import ReactiveExecutor
from fedotmas.engine.store import Store
from fedotmas.engine.terminate import Budget, Goal
from fedotmas.serialize import Graph, to_graph


async def test_seq_graph_edges():
    system, run = await run_flow(action(double) + action(triple), 2)
    g = to_graph(system, run)
    assert node(g, "double#1").kind == "action"
    assert node(g, "double#1").writes == ["double#1"]
    assert has_edge(g, "double#1", "triple#2")
    assert has_edge(g, "triple#2", "alias:out")


async def test_gather_fans_in():
    system, run = await run_flow(gather(action(double), action(triple)), 3)
    g = to_graph(system, run)
    assert node(g, "gather#1").kind == "gather"
    assert has_edge(g, "double#2", "gather#1")
    assert has_edge(g, "triple#3", "gather#1")


async def test_branch_untaken_arm_never_fires():
    system, run = await run_flow(
        branch("kind", {"x": action(pick_a), "y": action(pick_b)}), {"kind": "y"}
    )
    g = to_graph(system, run)
    assert node(g, "branch#1:route").kind == "branch.route"
    assert node(g, "pick_a#2").fired == 0
    assert node(g, "pick_b#3").fired == 1
    assert has_edge(g, "branch#1:route", "pick_b#3")
    assert not has_edge(g, "branch#1:route", "pick_a#2")


async def test_loop_iter_fires_each_round():
    system, run = await run_flow(
        action(bump).loop(until="done"), {"n": 0, "done": False}
    )
    g = to_graph(system, run)
    assert node(g, "loop#1:iter").kind == "loop.iter"
    assert node(g, "loop#1:iter").fired == 3
    assert node(g, "loop#1:done").fired == 1
    assert has_edge(g, "loop#1:iter", "loop#1:done")


async def test_board_graph():
    board = blackboard(
        Rule("score", score, reads="draft", writes="score"),
        Rule("gate", gate, reads="score", writes="verdict", when=["score", "!verdict"]),
    )
    system = board.compile()
    run = await ReactiveExecutor().run(
        system,
        Store(),
        seed=[Fact(tag="draft", value="a b c d e f")],
        terminate=Goal(lambda v: v.exists("verdict")) | Budget(50),
    )
    g = to_graph(system, run)
    assert node(g, "score").kind == "rule"
    assert node(g, "gate").writes == ["verdict"]
    assert has_edge(g, "score", "gate")


async def test_flow_over_board_is_one_node():
    inner = blackboard(Rule("count", count, reads="topic", writes="report"))
    flow = action(upper) + nest(inner, entry="topic", out="report")
    system, run = await run_flow(flow, "a b c")
    g = to_graph(system, run)
    assert node(g, "nest#2").kind == "nest"
    assert has_edge(g, "upper#1", "nest#2")
    assert not any(n.name == "count" for n in g.nodes)
    assert Graph.model_validate_json(g.model_dump_json()).nodes
