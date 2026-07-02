"""The arrow surface: combinators, state threading, declarative predicates, nesting."""

import functools

import pytest
from fedotmas import (
    Condition,
    Rule,
    RunError,
    action,
    blackboard,
    branch,
    gather,
    nest,
)
from fedotmas.engine import Fact, Goal, ReactiveExecutor, Store
from pydantic import BaseModel


class Patch(BaseModel):
    station: str
    done: bool


async def double(x, view):
    return x * 2


async def triple(x, view):
    return x * 3


async def echo(x, view):
    return x


async def bump(s, view):
    return {**s, "n": s["n"] + 1}


async def test_seq_pipes_left_into_right():
    run = await (action(double) + action(triple)).run(2)
    assert run.ok
    assert run.reason == "goal"
    assert run.value == 12


async def test_gather_collects_in_flow_order():
    run = await gather(action(double), action(triple), action(echo)).run(2)
    assert run.value == [4, 6, 2]


def test_gather_rejects_empty():
    with pytest.raises(ValueError, match="at least one flow"):
        gather()


async def test_branch_routes_by_callable():
    flow = branch(
        lambda n: "big" if n > 9 else "small",
        {"big": action(double), "small": action(triple)},
    )
    assert (await flow.run(10)).value == 20
    assert (await flow.run(1)).value == 3


async def test_branch_routes_by_state_key():
    async def via(s, view):
        return {**s, "via": s["route"]}

    flow = branch("route", {"a": action(via), "b": action(via)})
    run = await flow.run({"route": "b"})
    assert run.value == {"route": "b", "via": "b"}


async def test_branch_rejects_an_unknown_label():
    flow = branch("route", {"a": action(echo)})
    run = await flow.run({"route": "zzz"})
    assert not run.ok
    assert run.reason == "error"
    assert "not one of" in run.errors[0].value


async def test_loop_until_callable_feeds_output_back_in():
    async def inc(n, view):
        return n + 1

    run = await action(inc).loop(lambda n: n >= 3).run(0)
    assert run.value == 3


async def test_loop_until_condition_over_state():
    run = await action(bump).loop(Condition(key="n", op="gte", value=2)).run({"n": 0})
    assert run.value == {"n": 2}


async def test_loop_finishes_without_a_round_when_until_already_holds():
    run = await action(echo).loop(lambda s: True, budget=3).run(1)
    assert run.ok
    assert run.value == 1


async def test_into_threads_output_under_a_key():
    async def summarize(s):
        return f"sum:{s['ticket']}"

    flow = action(summarize).into("summary")
    run = await flow.run({"ticket": "x"})
    assert run.value == {"ticket": "x", "summary": "sum:x"}


async def test_merge_folds_a_structured_reply_into_state():
    async def patch(s):
        return Patch(station="tech", done=True)

    flow = action(patch).merge()
    run = await flow.run({"ticket": "y", "station": "triage"})
    assert run.value["station"] == "tech"
    assert run.value["done"] is True


@pytest.mark.parametrize(
    "kwargs",
    [
        pytest.param({"op": "gt"}, id="ordered-without-value"),
        pytest.param({"op": "truthy", "value": 5}, id="truthy-with-value"),
        pytest.param({"op": "exists", "value": 1}, id="exists-with-value"),
    ],
)
def test_condition_rejects_a_mismatched_value(kwargs):
    with pytest.raises(ValueError):
        Condition(key="k", **kwargs)


def test_condition_eq_none_stays_legal():
    assert Condition(key="k", op="eq", value=None).check({"k": None})


def test_condition_ordered_op_needs_the_key_present():
    with pytest.raises(ValueError, match="has no"):
        Condition(key="k", op="gt", value=1).check({})


def test_condition_composition_is_boolean_algebra():
    pred = Condition(key="a") & (Condition(key="b") | ~Condition(key="c"))
    assert pred.check({"a": 1, "b": 0, "c": 0})
    assert not pred.check({"a": 0, "b": 1, "c": 1})
    assert not pred.check({"a": 1, "b": 0, "c": 1})


def test_condition_tree_round_trips_through_json():
    pred = Condition(key="a") & ~Condition(key="b", op="exists")
    again = type(pred).model_validate_json(pred.model_dump_json(by_alias=True))
    assert again.check({"a": 1}) and not again.check({"a": 1, "b": 2})


async def test_loop_until_composed_condition():
    run = (
        await action(bump)
        .loop(Condition(key="n", op="gte", value=2) | Condition(key="stop"))
        .run({"n": 0})
    )
    assert run.value == {"n": 2}


async def test_action_name_shows_in_the_trace():
    run = await action(lambda x, view: echo(x, view), name="ident").run("hello")
    fired = {n for s in run.steps for n in s.fired}
    assert any(n.startswith("ident#") for n in fired)


async def test_outcome_repr_is_compact():
    run = await action(echo).run("hi")
    assert repr(run) == "Outcome(ok=True, reason='goal', value='hi')"


async def test_action_view_arg_is_optional():
    async def one_arg(x):
        return x * 2

    run = await action(one_arg).run(3)
    assert run.value == 6


async def test_action_lifts_an_unintrospectable_callable():
    async def add(a, b):
        return a + b

    run = await action(functools.partial(add, "pre-")).run("x")
    assert run.value == "pre-x"


async def test_branch_callable_selector_may_take_view():
    flow = branch(
        lambda n, view: "seen" if view.exists("in") else "blind",
        {"seen": action(double), "blind": action(triple)},
    )
    assert (await flow.run(2)).value == 4


async def test_loop_until_callable_may_take_view():
    async def inc(n):
        return n + 1

    run = await action(inc).loop(lambda n, view: n >= 2).run(0)
    assert run.value == 2


async def test_unwrap_returns_value_on_success():
    assert (await action(echo).run("hi")).unwrap() == "hi"


async def test_unwrap_raises_run_error_naming_the_reason():
    async def bad(x):
        return x["missing"]

    run = await action(bad).run({"a": 1})
    with pytest.raises(RunError, match="reason='error'"):
        run.unwrap()


async def test_nest_runs_a_flow_as_one_node():
    run = await nest(action(double), entry="a", out="b").run(3)
    assert run.value == 6


async def test_nest_budget_caps_a_non_quiescing_inner_board():
    async def spin(x, view):
        return view.count("tick") + 1

    spinner = blackboard(
        Rule(
            "spinner",
            fn=spin,
            reads="tick",
            writes="tick",
            when=lambda v: v.exists("tick"),
        ),
    )
    wrapped = nest(spinner.system, entry="tick", out="never", budget=5)
    run = await wrapped.run("start", budget=50)
    assert not run.ok
    assert run.reason == "error"
    assert "stopped (terminate)" in run.errors[0].value


async def test_join_waves_do_not_mix_across_unequal_branches():
    slow = action(echo, name="s1") + action(echo, name="s2")
    system = gather(action(double), slow).system(entry="in", out="out")
    store = Store()
    fed = False
    async for _ in ReactiveExecutor().stream(
        system,
        store,
        seed=[Fact(tag="in", value=1)],
        terminate=Goal(lambda v: v.count("out") >= 3),
    ):
        if not fed and store.snapshot().exists("out"):
            store.commit([Fact(tag="in", value=10, producer="feeder", step=99)])
            fed = True
    outs = [f.value for f in store.snapshot().query("out")]
    assert outs == [[2, 1], [20, 10]]


async def _second_wave(system, first, second):
    """Seed `first`, commit `second` into the same store once output appears, collect outs."""
    store = Store()
    fed = False
    async for _ in ReactiveExecutor().stream(
        system,
        store,
        seed=[Fact(tag="in", value=first)],
        terminate=Goal(lambda v: v.count("out") >= 2),
    ):
        if not fed and store.snapshot().exists("out"):
            store.commit([Fact(tag="in", value=second, producer="feeder", step=99)])
            fed = True
    return [f.value for f in store.snapshot().query("out")]


async def test_into_pairs_state_with_the_reply_of_its_own_wave():
    """Re-entry: a fresh state version must wait for its reply, not pair with the stale one."""

    async def shout(s, view):
        return s["topic"].upper()

    system = action(shout).into("reply").system(entry="in", out="out")
    waves = await _second_wave(system, {"topic": "a"}, {"topic": "b"})
    assert waves == [{"topic": "a", "reply": "A"}, {"topic": "b", "reply": "B"}]


async def test_merge_pairs_state_with_the_reply_of_its_own_wave():
    async def classify(s, view):
        return {"label": s["text"].upper()}

    system = action(classify).merge().system(entry="in", out="out")
    waves = await _second_wave(system, {"text": "a"}, {"text": "b"})
    assert waves == [{"text": "a", "label": "A"}, {"text": "b", "label": "B"}]


async def test_nest_wraps_a_mutually_recursive_board_as_one_node():
    """A bid/ask cycle the arrow surface cannot spell converges inside one typed step; the
    outer flow stays a straight arrow."""

    async def buy(ask, view):
        return round(min((view.value("bid") or 50) * 1.2, ask), 1)

    async def sell(bid, view):
        return round(max(bid, view.value("ask") * 0.9), 1)

    async def close(_, view):
        return {"price": view.value("bid"), "rounds": view.count("bid")}

    haggle = blackboard(
        Rule("buyer", buy, reads="ask", writes="bid", when=["ask"]),
        Rule("seller", sell, reads="bid", writes="ask", when=["bid"]),
        Rule(
            "referee",
            close,
            writes="deal",
            when=lambda v: v.exists("bid") and v.value("bid") >= v.value("ask"),
        ),
    )
    out = await nest(haggle, entry="ask", out="deal", budget=30).run(100.0)
    assert out.ok
    assert out.value == {"price": 81.0, "rounds": 3}
