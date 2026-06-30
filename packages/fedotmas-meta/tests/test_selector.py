"""The selector: one constrained pick over a caller-supplied menu of presets."""

from typing import Any

from fedotmas.engine import View
from fedotmas_meta import RoleSpec, select


class Stub:
    """A preset reduced to what the selector reads (name + hint); build is never reached here."""

    def __init__(self, name: str, hint: str) -> None:
        self.name = name
        self.hint = hint
        self.roles = (RoleSpec("x", "x"),)
        self.reserved = frozenset[str]()

    def build(self, fill: Any) -> Any:
        raise NotImplementedError


MENU = (Stub("blackboard", "shared state settles an answer"), Stub("debate", "voters"))


class FakeLLM:
    def __init__(self, reply) -> None:
        self._reply = reply

    async def complete(
        self, prompt: str, input: Any, view: View, returns: Any = str, tools: Any = None
    ) -> Any:
        return self._reply(prompt, input)


async def test_select_returns_a_menu_pattern():
    picked = await select(
        "settle a question", presets=MENU, llm=FakeLLM(lambda p, i: "blackboard")
    )
    assert picked.pattern == "blackboard"


async def test_select_menu_lists_every_hint():
    seen = {}

    def reply(p, i):
        seen["prompt"] = p
        return "blackboard"

    await select("t", presets=MENU, llm=FakeLLM(reply))
    assert all(f"- {p.name}: {p.hint}" in seen["prompt"] for p in MENU)
