"""The blackboard surface: produce-once, when triggers, re-fire identity, validation."""

import pytest
from fedotmas import Condition, Rule, action, blackboard
from fedotmas.engine import AuctionSelect, Fact, Goal, ReactiveExecutor, Store, System


async def bump(value, view):
    return value + 1


async def mark(value, view):
    return True


async def test_rule_fn_view_arg_is_optional():
    async def one_arg(value):
        return value + 1

    board = blackboard(Rule("one", fn=one_arg, reads="seed", writes="a"))
    out = await board.run({"seed": 1}, goal="a")
    assert out.ok
    assert out.value == 2


async def test_produce_once_chains_without_triggers():
    board = blackboard(
        Rule("one", fn=bump, reads="seed", writes="a"),
        Rule("two", fn=bump, reads="a", writes="b"),
    )
    out = await board.run({"seed": 1}, goal="b")
    assert out.ok
    assert out.value == 3


async def test_produce_once_does_not_refire():
    board = blackboard(Rule("one", fn=bump, reads="seed", writes="a"))
    out = await board.run({"seed": 1}, goal="missing", budget=5)
    assert out.reason == "stalled"
    assert sum(s.fired.count("one") for s in out.steps) == 1


async def test_when_veto_blocks_activation():
    board = blackboard(Rule("r", fn=mark, writes="x", when=["go", "!stop"]))
    blocked = await board.run({"go": 1, "stop": 1}, goal="x", budget=3)
    assert blocked.reason == "stalled"
    clear = await board.run({"go": 1}, goal="x")
    assert clear.ok


async def test_positive_when_tags_join_the_refire_identity():
    seen = []

    async def log(value, view):
        seen.append(view.count("sig"))
        return len(seen)

    board = blackboard(Rule("r", fn=log, writes="out", when=["sig"]))
    store = Store()
    fed = False
    async for _ in ReactiveExecutor().stream(
        board.system(),
        store,
        seed=[Fact(tag="sig", value=1)],
        terminate=[Goal(lambda v: v.count("out") >= 2)],
    ):
        if not fed:
            store.commit([Fact(tag="sig", value=2, producer="feeder", step=50)])
            fed = True
    assert seen == [1, 2]


async def test_when_condition_compares_a_view_value():
    board = blackboard(
        Rule("r", fn=mark, writes="x", when=Condition(key="score", op="gte", value=3))
    )
    low = await board.run({"score": 1}, goal="x", budget=3)
    assert low.reason == "stalled"
    high = await board.run({"score": 5}, goal="x")
    assert high.ok


async def test_when_composed_condition_spans_two_facts():
    when = Condition(key="ready") & ~Condition(key="halt", op="exists")
    board = blackboard(Rule("r", fn=mark, writes="x", when=when))
    blocked = await board.run({"ready": True, "halt": 1}, goal="x", budget=3)
    assert blocked.reason == "stalled"
    clear = await board.run({"ready": True}, goal="x")
    assert clear.ok


async def test_callable_when_without_reads_fires_at_most_once():
    board = blackboard(Rule("r", fn=mark, writes="out", when=lambda v: True))
    out = await board.run({}, goal="missing", budget=5)
    assert out.reason == "stalled"
    assert sum(s.fired.count("r") for s in out.steps) == 1


async def test_outcome_can_reach_the_goal_past_an_error():
    async def fail(value, view):
        raise RuntimeError("boom")

    board = blackboard(
        Rule("ok", fn=mark, reads="seed", writes="goal"),
        Rule("bad", fn=fail, reads="seed", writes="other"),
        halt_on_error=False,
    )
    out = await board.run({"seed": 1}, goal="goal")
    assert out.reason == "goal"
    assert not out.ok
    assert out.errors


async def test_a_repair_rule_reacts_to_another_rules_error():
    async def flaky(value):
        raise ValueError("no plan")

    async def repair(msg):
        return f"fallback after {msg}"

    board = blackboard(
        Rule("planner", fn=flaky, reads="task", writes="out"),
        Rule("medic", fn=repair, reads="error:planner", writes="out"),
        halt_on_error=False,
    )
    out = await board.run({"task": "go"}, goal="out")
    assert out.value == "fallback after no plan"
    assert out.reason == "goal"
    assert not out.ok


async def test_a_rule_runs_a_flow_as_its_body():
    board = blackboard(
        Rule("prep", fn=bump, reads="task", writes="topic"),
        Rule(
            "research",
            nest=action(bump) + action(bump),
            reads="topic",
            writes="report",
        ),
    )
    out = await board.run({"task": 1}, goal="report")
    assert out.ok
    assert out.value == 4


async def test_a_board_nests_another_board_as_a_rule():
    inner = blackboard(Rule("solve", fn=bump, reads="q", writes="a"))
    outer = blackboard(
        Rule("delegate", nest=inner, reads="task", writes="answer", entry="q", out="a")
    )
    out = await outer.run({"task": 41}, goal="answer")
    assert out.ok
    assert out.value == 42


async def test_a_nest_rule_failure_carries_the_inner_causes():
    async def die(q):
        raise ValueError("inner boom")

    inner = blackboard(Rule("worker", fn=die, reads="q", writes="a"))
    outer = blackboard(
        Rule("sub", nest=inner, reads="task", writes="answer", entry="q", out="a")
    )
    out = await outer.run({"task": 1}, goal="answer")
    assert out.reason == "error"
    err = out.errors[0]
    assert err.tag == "error:sub"
    assert "inner system failed" in err.value
    [cause] = err.meta["causes"]
    assert cause["producer"] == "worker"
    assert cause["meta"]["type"] == "ValueError"


def test_board_system_rejects_an_unwritten_out():
    board = blackboard(Rule("r", fn=bump, reads="a", writes="b"))
    with pytest.raises(ValueError, match="no rule writes"):
        board.system(out="c")
    assert board.system(out="b").nodes


async def test_a_board_policy_holds_an_auction_each_superstep():
    def says(name):
        async def fn(value, view):
            return name

        return fn

    bids = {"hi": 0.9, "lo": 0.1}
    board = blackboard(
        Rule("hi", fn=says("hi"), reads="seed", writes="out"),
        Rule("lo", fn=says("lo"), reads="seed", writes="out"),
        policy=AuctionSelect(key=lambda n, v: bids[n.name]),
    )
    out = await board.run({"seed": 1}, goal="out")
    assert out.ok
    assert out.value == "hi"
    assert [s.fired for s in out.steps if s.fired] == [["hi"]]


def test_meta_rides_to_the_card():
    board = blackboard(Rule("r", fn=mark, reads="a", writes="b", meta={"bid": 3}))
    assert board.system().nodes[0].describe().meta == {"bid": 3}


@pytest.mark.parametrize(
    "rule",
    [
        pytest.param(Rule("r", fn=bump, reads="a b", writes="c"), id="multi-reads"),
        pytest.param(Rule("r", fn=bump, writes="c", when=["a", "!a"]), id="when-clash"),
        pytest.param(Rule("r", fn=bump, writes=""), id="no-writes"),
        pytest.param(Rule("r", writes="c"), id="no-step"),
        pytest.param(
            Rule("r", fn=bump, writes="c", when=["a", ""]), id="empty-when-tag"
        ),
        pytest.param(Rule("r", fn=bump, writes="c", when="tag"), id="bare-string-when"),
        pytest.param(Rule("r", fn=bump, nest=System([]), writes="c"), id="fn-and-nest"),
        pytest.param(
            Rule("r", nest=System([]), writes="c", entry=""), id="nest-empty-entry"
        ),
    ],
)
def test_rule_validation(rule):
    with pytest.raises(ValueError):
        blackboard(rule)


def test_duplicate_rule_names_rejected():
    with pytest.raises(ValueError, match="duplicate rule names"):
        blackboard(Rule("r", fn=bump, writes="a"), Rule("r", fn=bump, writes="b"))


async def test_back_edge_rule_re_runs_the_pipeline_to_the_goal():
    """A rule appending a NEW version of the entry fact runs the chain again as a next wave;
    the append-only log doubles as the attempt history the worker reads its effort off."""

    async def work(task, view):
        return view.count("task")

    async def resubmit(draft, view):
        return draft

    async def accept(draft, view):
        return draft

    board = blackboard(
        Rule("work", fn=work, reads="task", writes="draft", when=["task"]),
        Rule(
            "resubmit",
            fn=resubmit,
            reads="draft",
            writes="task",
            when=lambda v: v.exists("draft") and v.value("draft") < 3,
        ),
        Rule(
            "accept",
            fn=accept,
            reads="draft",
            writes="done",
            when=lambda v: v.exists("draft") and v.value("draft") >= 3,
        ),
    )
    out = await board.run({"task": 0}, goal="done")
    assert out.ok
    assert out.value == 3
    assert out.view.count("task") == 3
