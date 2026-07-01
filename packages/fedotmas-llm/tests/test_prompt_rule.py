"""PromptRule: a blackboard rule whose body is a prompt, bound by the run or per rule."""

from typing import Any

import pytest
from fedotmas import Rule, blackboard
from fedotmas.engine import View
from fedotmas_llm import Call, PromptRule


class FakeLLM:
    def __init__(self, reply) -> None:
        self._reply = reply

    async def complete(self, call: Call, view: View) -> Any:
        return self._reply(call.prompt, call.input)


async def test_prompt_rule_uses_the_run_scoped_llm():
    board = blackboard(PromptRule("r", prompt="say", reads="q", writes="ans"))
    out = await board.run(
        {"q": "hi"},
        goal="ans",
        bind={"llm": FakeLLM(lambda p, content: f"{p}:{content}")},
    )
    assert out.value == "say:hi"


async def test_per_rule_llm_overrides_the_run_default():
    board = blackboard(
        PromptRule(
            "r",
            prompt="say",
            reads="q",
            writes="ans",
            llm=FakeLLM(lambda p, c: "rule"),
        )
    )
    out = await board.run(
        {"q": "hi"}, goal="ans", bind={"llm": FakeLLM(lambda p, c: "run")}
    )
    assert out.value == "rule"


async def test_prompt_and_code_rules_share_one_board():
    async def shout(text, view):
        return text.upper()

    board = blackboard(
        PromptRule("draft", prompt="D", reads="topic", writes="draft"),
        Rule("loud", fn=shout, reads="draft", writes="ans"),
    )
    out = await board.run(
        {"topic": "tea"}, goal="ans", bind={"llm": FakeLLM(lambda p, c: f"{p}:{c}")}
    )
    assert out.value == "D:TEA"


def test_prompt_rule_without_a_backend_fails_at_compile_time():
    board = blackboard(PromptRule("r", prompt="say", writes="ans", when=["q"]))
    with pytest.raises(ValueError, match="no llm bound"):
        board.compile()


def test_prompt_rule_requires_a_prompt():
    with pytest.raises(ValueError, match="prompt= is required"):
        blackboard(PromptRule("r", reads="q", writes="ans"))


def test_prompt_rule_rejects_a_code_body():
    async def fn(value, view):
        return value

    with pytest.raises(ValueError, match="takes no fn="):
        blackboard(PromptRule("r", prompt="p", fn=fn, writes="ans"))
