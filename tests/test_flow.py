"""The arrow surface: combinators, state threading, declarative predicates, nesting."""

from typing import Any

import pytest
from pydantic import BaseModel

from fedotmas.engine import Fact, Goal, ReactiveExecutor, Store, View
from fedotmas.sdk import (
    Condition,
    Rule,
    action,
    agent,
    blackboard,
    branch,
    gather_all,
    nest,
)


class FakeLLM:
    def __init__(self, reply) -> None:
        self._reply = reply

    async def complete(
        self, prompt: str, input: Any, view: View, returns: Any = str
    ) -> Any:
        return self._reply(prompt, input)


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


async def test_par_pairs_both_outputs():
    run = await (action(double) * action(triple)).run(1)
    assert run.value == (2, 3)


async def test_gather_all_collects_in_flow_order():
    run = await gather_all(action(double), action(triple), action(echo)).run(2)
    assert run.value == [4, 6, 2]


def test_gather_all_rejects_empty():
    with pytest.raises(ValueError, match="at least one flow"):
        gather_all()


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


async def test_into_threads_state_through_a_template():
    note = agent(
        "note",
        prompt="Restate the ticket.",
        input="Ticket: {ticket}",
        takes=dict,
        returns=str,
    ).into("summary")
    run = await note.run(
        {"ticket": "double charge"},
        llm=FakeLLM(lambda p, content: f"noted({content})"),
    )
    assert run.ok
    assert run.value == {
        "ticket": "double charge",
        "summary": "noted(Ticket: double charge)",
    }


async def test_merge_branch_loop_make_a_handoff():
    hop = agent(
        "hop",
        prompt="Handle and hand off.",
        input="{ticket}",
        takes=dict,
        returns=Patch,
    ).merge()
    flow = branch("station", {"triage": hop, "tech": hop}).loop(until="done")
    hops = iter([Patch(station="tech", done=False), Patch(station="tech", done=True)])
    run = await flow.run(
        {"ticket": "app crash", "station": "triage"},
        llm=FakeLLM(lambda p, content: next(hops)),
        budget=8,
    )
    assert run.ok
    assert run.value["done"] and run.value["station"] == "tech"


async def test_a_failing_node_is_an_error_outcome():
    bad = agent("bad", prompt="x", input="{missing_key}", takes=dict, returns=str)
    run = await bad.run({"ticket": "x"}, llm=FakeLLM(lambda p, c: c))
    assert not run.ok
    assert run.reason == "error"
    assert run.errors[0].producer.startswith("bad")


def test_an_unbound_llm_fails_at_compile_time():
    with pytest.raises(ValueError, match="no llm bound"):
        agent("loose", prompt="x").system(entry="in", out="out")


async def test_labels_make_a_validated_classifier():
    pick = agent("pick", prompt="route", labels=["a", "b"])
    run = await pick.run("q", llm=FakeLLM(lambda p, c: "a"))
    assert run.value == "a"
    run = await pick.run("q", llm=FakeLLM(lambda p, c: "zzz"))
    assert not run.ok
    assert "not in" in run.errors[0].value


def test_labels_do_not_combine_with_returns():
    with pytest.raises(ValueError, match="does not combine with returns="):
        agent("x", prompt="p", labels=["a"], returns=int)  # type: ignore


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


async def test_action_name_shows_in_the_trace():
    run = await action(lambda x, view: echo(x, view), name="ident").run("hello")
    fired = {n for s in run.steps for n in s.fired}
    assert any(n.startswith("ident#") for n in fired)


async def test_outcome_repr_is_compact():
    run = await action(echo).run("hi")
    assert repr(run) == "Outcome(ok=True, reason='goal', value='hi')"


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


@pytest.mark.xfail(
    strict=True,
    reason="joins are not wave-aligned: a second wave over unequal branch lengths "
    "emits a mixed tuple; needs an epoch notion",
)
async def test_join_waves_do_not_mix_across_unequal_branches():
    slow = action(echo, name="s1") + action(echo, name="s2")
    system = (action(double) * slow).system(entry="in", out="out")
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
    assert outs == [(2, 1), (20, 10)]
