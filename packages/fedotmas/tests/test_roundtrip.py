"""from_blueprint: rebuild a runnable System from its declarative floor, the inverse of
to_blueprint. The round-trip is the probe: a rebuilt system has the same blueprint (structural
fixed point) and runs to the same output, given the opaque bodies by name. RED until
from_blueprint is implemented; this file is the contract."""

import pytest
from _helpers import bump, double, gate, pick_a, pick_b, score, triple
from fedotmas import Rule, action, blackboard, branch, gather
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


def test_missing_body_is_named_error():
    bp = to_blueprint(action(double).system(entry="in", out="out"))
    with pytest.raises(ReconstructError):
        from_blueprint(bp, Deps(bodies={}))
