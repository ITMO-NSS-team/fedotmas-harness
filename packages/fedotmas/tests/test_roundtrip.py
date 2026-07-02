"""from_blueprint: rebuild a runnable System from its declarative floor, the inverse of
to_blueprint. The round-trip is the probe: a rebuilt system has the same blueprint (structural
fixed point) and runs to the same output, given the opaque bodies by name. RED until
from_blueprint is implemented; this file is the contract."""

import pytest
from _helpers import bump, count, double, gate, pick_a, pick_b, score, triple, upper
from fedotmas import Rule, action, blackboard, branch, gather, nest
from fedotmas.engine.contract import Fact
from fedotmas.engine.executor import ReactiveExecutor
from fedotmas.engine.store import Store
from fedotmas.engine.terminate import Budget, Goal
from fedotmas.serialize import Deps, ReconstructError, from_blueprint, to_blueprint


async def _out(system, seed_tag, value, goal):
    """Run a System on one seed and read the goal fact, the behavioural half of the round-trip."""
    run = await ReactiveExecutor().run(
        system,
        Store(),
        seed=[Fact(tag=seed_tag, value=value)],
        terminate=Goal(lambda v: v.exists(goal)) | Budget(50),
    )
    return run.view.value(goal)


async def test_roundtrip_seq():
    system = (action(double) + action(triple)).system(entry="in", out="out")
    bp = to_blueprint(system)
    rebuilt = from_blueprint(bp, Deps(bodies={"double": double, "triple": triple}))
    assert to_blueprint(rebuilt) == bp
    assert await _out(rebuilt, "in", 2, "out") == await _out(system, "in", 2, "out")


async def test_roundtrip_gather():
    system = gather(action(double), action(triple)).system(entry="in", out="out")
    bp = to_blueprint(system)
    rebuilt = from_blueprint(bp, Deps(bodies={"double": double, "triple": triple}))
    assert to_blueprint(rebuilt) == bp
    assert await _out(rebuilt, "in", 3, "out") == await _out(system, "in", 3, "out")


async def test_roundtrip_branch_state_key():
    flow = branch("kind", {"x": action(pick_a), "y": action(pick_b)})
    system = flow.system(entry="in", out="out")
    bp = to_blueprint(system)
    rebuilt = from_blueprint(bp, Deps(bodies={"pick_a": pick_a, "pick_b": pick_b}))
    assert to_blueprint(rebuilt) == bp
    v = {"kind": "y"}
    assert await _out(rebuilt, "in", v, "out") == await _out(system, "in", v, "out")


async def test_roundtrip_loop_state_key():
    system = action(bump).loop(until="done").system(entry="in", out="out")
    bp = to_blueprint(system)
    rebuilt = from_blueprint(bp, Deps(bodies={"bump": bump}))
    assert to_blueprint(rebuilt) == bp
    v = {"n": 0, "done": False}
    assert await _out(rebuilt, "in", v, "out") == await _out(system, "in", v, "out")


async def test_roundtrip_board():
    board = blackboard(
        Rule("score", score, reads="draft", writes="score"),
        Rule("gate", gate, reads="score", writes="verdict", when=["score", "!verdict"]),
    )
    system = board.compile()
    bp = to_blueprint(system)
    rebuilt = from_blueprint(bp, Deps(bodies={"score": score, "gate": gate}))
    assert to_blueprint(rebuilt) == bp
    draft = "a b c d e f"
    assert await _out(rebuilt, "draft", draft, "verdict") == await _out(
        system, "draft", draft, "verdict"
    )


async def test_roundtrip_nest_over_board():
    inner = blackboard(Rule("count", count, reads="topic", writes="report"))
    flow = action(upper) + nest(inner, entry="topic", out="report")
    system = flow.system(entry="in", out="out")
    bp = to_blueprint(system)
    rebuilt = from_blueprint(bp, Deps(bodies={"upper": upper, "count": count}))
    assert to_blueprint(rebuilt) == bp
    assert await _out(rebuilt, "in", "a b c", "out") == await _out(
        system, "in", "a b c", "out"
    )


async def test_roundtrip_loop_keeps_non_default_budget():
    """The per-round superstep cap rides in the blueprint, so a rebuilt loop keeps it instead
    of silently resetting to the default 100."""
    system = action(bump).loop(until="done", budget=7).system(entry="in", out="out")
    bp = to_blueprint(system)
    it = next(n for n in bp.nodes if n.kind == "loop.iter")
    assert it.params["budget"] == 7
    rebuilt = from_blueprint(bp, Deps(bodies={"bump": bump}))
    assert to_blueprint(rebuilt) == bp
    v = {"n": 0, "done": False}
    assert await _out(rebuilt, "in", v, "out") == await _out(system, "in", v, "out")


async def test_roundtrip_nest_keeps_non_default_budget():
    """A non-default inner budget on nest survives the round-trip."""
    inner = blackboard(Rule("count", count, reads="topic", writes="report"))
    flow = action(upper) + nest(inner, entry="topic", out="report", budget=13)
    system = flow.system(entry="in", out="out")
    bp = to_blueprint(system)
    nestnode = next(n for n in bp.nodes if n.kind == "nest")
    assert nestnode.params["budget"] == 13
    rebuilt = from_blueprint(bp, Deps(bodies={"upper": upper, "count": count}))
    assert to_blueprint(rebuilt) == bp
    assert await _out(rebuilt, "in", "a b c", "out") == await _out(
        system, "in", "a b c", "out"
    )


def test_missing_body_is_named_error():
    bp = to_blueprint(action(double).system(entry="in", out="out"))
    with pytest.raises(ReconstructError):
        from_blueprint(bp, Deps(bodies={}))


def test_callable_until_is_named_error():
    system = action(bump).loop(until=lambda s: s["done"]).system(entry="in", out="out")
    with pytest.raises(ReconstructError):
        from_blueprint(to_blueprint(system), Deps(bodies={"bump": bump}))


async def test_roundtrip_loop_over_branch_with_a_nested_loop():
    """Deep nonlinearity stays declarative: a loop over a branch whose one case is itself a
    loop (a solver that rewrites its own route key to escalate) rebuilds and runs the same."""

    async def fast_step(s):
        tries = s["tries"] + 1
        mode = "careful" if tries >= 2 else "fast"
        return {**s, "tries": tries, "mode": mode, "solved": s["n"] <= 2}

    async def careful_step(s):
        sub = s["sub"] + 1
        return {**s, "sub": sub, "sub_done": sub >= s["n"], "solved": sub >= s["n"]}

    flow = branch(
        "mode",
        {
            "fast": action(fast_step),
            "careful": action(careful_step).loop(until="sub_done"),
        },
    ).loop(until="solved")
    system = flow.system(entry="in", out="out")

    bp = to_blueprint(system)
    outer = next(n for n in bp.nodes if n.kind == "loop.iter")
    assert outer.inner is not None
    assert any(n.kind == "loop.iter" for n in outer.inner.nodes)

    rebuilt = from_blueprint(
        bp, Deps(bodies={"fast_step": fast_step, "careful_step": careful_step})
    )
    assert to_blueprint(rebuilt) == bp
    v = {"n": 4, "tries": 0, "sub": 0, "mode": "fast", "solved": False}
    assert await _out(rebuilt, "in", v, "out") == await _out(system, "in", v, "out")
