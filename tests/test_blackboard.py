"""The blackboard surface: produce-once, when triggers, re-fire identity, validation."""

from typing import Any

import pytest

from fedotmas.engine import Fact, Goal, ReactiveExecutor, Store, View
from fedotmas.sdk import Rule, blackboard


class FakeLLM:
    def __init__(self, reply) -> None:
        self._reply = reply

    async def complete(
        self, prompt: str, input: Any, view: View, returns: Any = str
    ) -> Any:
        return self._reply(prompt, input)


async def bump(value, view):
    return value + 1


async def mark(value, view):
    return True


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
        board.system,
        store,
        seed=[Fact(tag="sig", value=1)],
        terminate=Goal(lambda v: v.count("out") >= 2),
    ):
        if not fed:
            store.commit([Fact(tag="sig", value=2, producer="feeder", step=50)])
            fed = True
    assert seen == [1, 2]


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
    )
    out = await board.run({"seed": 1}, goal="goal", halt_on_error=False)
    assert out.reason == "goal"
    assert not out.ok
    assert out.errors


async def test_prompt_rule_uses_the_board_default_llm():
    board = blackboard(
        Rule("r", prompt="say", reads="q", writes="ans"),
        llm=FakeLLM(lambda p, content: f"{p}:{content}"),
    )
    out = await board.run({"q": "hi"}, goal="ans")
    assert out.value == "say:hi"


def test_prompt_rule_without_a_backend_fails_at_compile_time():
    board = blackboard(Rule("r", prompt="say", writes="ans", when=["q"]))
    with pytest.raises(ValueError, match="no llm bound"):
        board.compile()


def test_meta_rides_to_the_card():
    board = blackboard(Rule("r", fn=mark, reads="a", writes="b", meta={"bid": 3}))
    assert board.system.nodes[0].describe().meta == {"bid": 3}


@pytest.mark.parametrize(
    "rule",
    [
        pytest.param(Rule("r", fn=bump, reads="a b", writes="c"), id="multi-reads"),
        pytest.param(Rule("r", fn=bump, writes="c", when=["a", "!a"]), id="when-clash"),
        pytest.param(Rule("r", fn=bump, writes=""), id="no-writes"),
        pytest.param(Rule("r", writes="c"), id="no-step"),
        pytest.param(Rule("r", fn=bump, prompt="p", writes="c"), id="two-steps"),
        pytest.param(
            Rule("r", fn=bump, writes="c", when=["a", ""]), id="empty-when-tag"
        ),
        pytest.param(Rule("r", fn=bump, writes="c", when="tag"), id="bare-string-when"),
    ],
)
def test_rule_validation(rule):
    with pytest.raises(ValueError):
        blackboard(rule)


def test_duplicate_rule_names_rejected():
    with pytest.raises(ValueError, match="duplicate rule names"):
        blackboard(Rule("r", fn=bump, writes="a"), Rule("r", fn=bump, writes="b"))
