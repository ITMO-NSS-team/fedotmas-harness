"""to_graph: a finished run projected to its dataflow graph, surface-agnostic over the floor."""

from fedotmas import Rule, action, blackboard, branch, gather, nest
from fedotmas.engine.contract import Fact
from fedotmas.engine.executor import ReactiveExecutor
from fedotmas.engine.store import Store
from fedotmas.engine.terminate import Budget, Goal
from fedotmas.serialize import Graph, to_graph


async def double(x):
    return x * 2


async def triple(x):
    return x * 3


async def pick_a(s):
    return "A"


async def pick_b(s):
    return "B"


async def bump(s):
    n = s["n"] + 1
    return {"n": n, "done": n >= 3}


async def score(d):
    return len(d.split())


async def gate(n):
    return "ship" if n >= 5 else "revise"


async def upper(s):
    return s.upper()


async def count(topic):
    return len(topic.split())


async def _run_flow(flow, value):
    system = flow.system(entry="in", out="out")
    run = await ReactiveExecutor().run(
        system,
        Store(),
        seed=[Fact(tag="in", value=value)],
        terminate=Goal(lambda v: v.exists("out")) | Budget(50),
    )
    return system, run


def _node(g, name):
    return next(n for n in g.nodes if n.name == name)


def _has_edge(g, src, dst):
    return any(e.src == src and e.dst == dst for e in g.edges)


async def test_seq_graph_edges():
    system, run = await _run_flow(action(double) + action(triple), 2)
    g = to_graph(system, run)
    assert _node(g, "double#1").kind == "action"
    assert _node(g, "double#1").writes == ["double#1"]
    assert _has_edge(g, "double#1", "triple#2")
    assert _has_edge(g, "triple#2", "alias:out")


async def test_gather_fans_in():
    system, run = await _run_flow(gather(action(double), action(triple)), 3)
    g = to_graph(system, run)
    assert _node(g, "gather#1").kind == "gather"
    assert _has_edge(g, "double#2", "gather#1")
    assert _has_edge(g, "triple#3", "gather#1")


async def test_branch_untaken_arm_never_fires():
    system, run = await _run_flow(
        branch("kind", {"x": action(pick_a), "y": action(pick_b)}), {"kind": "y"}
    )
    g = to_graph(system, run)
    assert _node(g, "branch#1:route").kind == "branch.route"
    assert _node(g, "pick_a#2").fired == 0
    assert _node(g, "pick_b#3").fired == 1
    assert _has_edge(g, "branch#1:route", "pick_b#3")
    assert not _has_edge(g, "branch#1:route", "pick_a#2")


async def test_loop_iter_fires_each_round():
    system, run = await _run_flow(
        action(bump).loop(until="done"), {"n": 0, "done": False}
    )
    g = to_graph(system, run)
    assert _node(g, "loop#1:iter").kind == "loop.iter"
    assert _node(g, "loop#1:iter").fired == 3
    assert _node(g, "loop#1:done").fired == 1
    assert _has_edge(g, "loop#1:iter", "loop#1:done")


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
    assert _node(g, "score").kind == "rule"
    assert _node(g, "gate").writes == ["verdict"]
    assert _has_edge(g, "score", "gate")


async def test_flow_over_board_is_one_node():
    inner = blackboard(Rule("count", count, reads="topic", writes="report"))
    flow = action(upper) + nest(inner, entry="topic", out="report")
    system, run = await _run_flow(flow, "a b c")
    g = to_graph(system, run)
    assert _node(g, "nest#2").kind == "nest"
    assert _has_edge(g, "upper#1", "nest#2")
    assert not any(n.name == "count" for n in g.nodes)
    assert Graph.model_validate_json(g.model_dump_json()).nodes
