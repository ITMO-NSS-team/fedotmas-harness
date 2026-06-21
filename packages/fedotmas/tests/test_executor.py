"""Superstep semantics: edge-triggering, event waves, seeds, errors, warm-store re-runs."""

import pytest
from fedotmas.engine import (
    Budget,
    Fact,
    Goal,
    ReactiveExecutor,
    Result,
    Status,
    Store,
    System,
    as_node,
)
from fedotmas import action, gather


async def double(x, view):
    return x * 2


async def triple(x, view):
    return x * 3


async def boom(x, view):
    raise RuntimeError("boom")


async def fine(x, view):
    return "fine"


def emit(tag):
    async def fn(input, view):
        return Result(writes=[Fact(tag=tag, value=len(input))])

    return fn


async def test_edge_trigger_fires_once_per_matched_set():
    inputs = []

    async def fn(input, view):
        inputs.append([f.key for f in input])
        return Result(writes=[Fact(tag="out", value=1)])

    system = System([as_node(fn, name="n", reads="in")])
    run = await ReactiveExecutor().run(system, Store(), seed=[Fact(tag="in", value=1)])
    assert inputs == [[("in", -1, "seed")]]
    assert run.reason == "quiescence"
    assert run.steps[-1].fired == []


async def test_a_new_version_re_arms_the_node():
    system = System([as_node(emit("tick"), name="t", reads="tick")])
    run = await ReactiveExecutor().run(
        system, Store(), seed=[Fact(tag="tick")], terminate=Budget(3)
    )
    assert [s.fired for s in run.steps] == [["t"], ["t"], ["t"]]


async def test_a_node_without_reads_fires_at_most_once_per_run():
    system = System([as_node(emit("out"), name="gen", trigger=lambda v: True)])
    run = await ReactiveExecutor().run(system, Store())
    assert [s.fired for s in run.steps] == [["gen"], []]
    assert run.reason == "quiescence"


async def test_gather_join_refires_on_a_second_input_wave():
    system = gather(action(double), action(triple)).system(entry="in", out="out")
    store = Store()
    fed = False
    async for _ in ReactiveExecutor().stream(
        system,
        store,
        seed=[Fact(tag="in", value=1)],
        terminate=Goal(lambda v: v.count("out") >= 2),
    ):
        if not fed and store.snapshot().exists("out"):
            store.commit([Fact(tag="in", value=10, producer="feeder", step=99)])
            fed = True
    outs = [f.value for f in store.snapshot().query("out")]
    assert outs == [[2, 3], [20, 30]]


async def test_budget_counts_the_run_index_not_the_store_step():
    store = Store()
    system = System([as_node(emit("tick"), name="t", reads="tick")])
    await ReactiveExecutor().run(
        system, store, seed=[Fact(tag="tick")], terminate=Budget(4)
    )
    clock = store.next_step()
    assert clock > 0
    run = await ReactiveExecutor().run(system, store, terminate=Budget(4))
    assert len(run.steps) == 4
    assert run.steps[0].index == 0
    assert run.steps[0].step == clock


async def test_seed_stamping_on_a_fresh_store():
    store = Store()
    system = System([as_node(emit("out"), name="n", reads="in")])
    await ReactiveExecutor().run(
        system,
        store,
        seed=[Fact(tag="in", value=1, producer="feeder", step=7), Fact(tag="cfg")],
        terminate=Goal(lambda v: v.exists("out")),
    )
    view = store.snapshot()
    f_in, f_cfg = view.get("in"), view.get("cfg")
    assert f_in is not None and f_in.key == ("in", 7, "feeder")
    assert f_cfg is not None and f_cfg.key == ("cfg", -1, "seed")


async def test_default_seeds_get_fresh_keys_on_a_warm_store():
    store = Store()
    system = System([as_node(emit("out"), name="n", reads="in")])
    goal = Goal(lambda v: v.exists("out"))
    await ReactiveExecutor().run(
        system, store, seed=[Fact(tag="in", value=1)], terminate=goal
    )
    await ReactiveExecutor().run(
        system, store, seed=[Fact(tag="in", value=2)], terminate=goal
    )
    keys = [f.key for f in store.snapshot().query("in")]
    assert keys[0] == ("in", -1, "seed")
    assert keys[1][1] >= 0
    assert len(set(keys)) == 2


async def test_sequential_runs_re_derive_and_converge():
    system = gather(action(double), action(triple)).system(entry="in", out="out")
    store = Store()
    await ReactiveExecutor().run(
        system,
        store,
        seed=[Fact(tag="in", value=1)],
        terminate=Goal(lambda v: v.exists("out")),
    )
    await ReactiveExecutor().run(
        system,
        store,
        seed=[Fact(tag="in", value=10)],
        terminate=Goal(lambda v: v.value("out") == [20, 30]),
    )
    view = store.snapshot()
    assert view.value("out") == [20, 30]
    keys = [f.key for f in view.query("*")]
    assert len(keys) == len(set(keys))


async def test_halt_on_error_ends_the_run_with_the_traceback():
    async def fail(input, view):
        raise RuntimeError("boom")

    system = System([as_node(fail, name="bad", reads="in")])
    store = Store()
    run = await ReactiveExecutor().run(system, store, seed=[Fact(tag="in")])
    assert run.status is Status.ERROR
    assert run.reason == "error"
    err = run.steps[-1].errors[0]
    assert err.tag == "error:bad"
    assert err.value == "boom"
    assert "RuntimeError" in err.meta["traceback"]
    assert store.snapshot().exists("error:bad")


async def test_halt_on_error_false_keeps_the_rest_running():
    run = await gather(action(boom), action(fine)).run(
        "x", halt_on_error=False, budget=5
    )
    assert not run.ok
    assert run.reason == "stalled"
    assert [e.tag.startswith("error:boom") for e in run.errors] == [True]
    fired = {n for s in run.steps for n in s.fired}
    assert any(n.startswith("fine") for n in fired)


def test_duplicate_node_names_rejected():
    nodes = [as_node(emit("x"), name="dup", reads="a"), as_node(emit("y"), name="dup")]
    with pytest.raises(ValueError, match="duplicate node names"):
        System(nodes)
