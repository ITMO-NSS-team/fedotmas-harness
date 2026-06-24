"""The selector: a constrained pick over the catalog menu (one family while presets refactor)."""

from typing import Any

from fedotmas.engine import View
from fedotmas_meta import select
from fedotmas_meta.presets import catalog, get


class FakeLLM:
    def __init__(self, reply) -> None:
        self._reply = reply

    async def complete(
        self, prompt: str, input: Any, view: View, returns: Any = str
    ) -> Any:
        return self._reply(prompt, input)


async def test_select_returns_a_catalog_pattern():
    picked = await select("settle a question", llm=FakeLLM(lambda p, i: "blackboard"))
    assert picked.pattern == "blackboard"
    assert get(picked.pattern).roles


async def test_select_menu_lists_every_hint():
    seen = {}

    def reply(p, i):
        seen["prompt"] = p
        return "blackboard"

    await select("t", llm=FakeLLM(reply))
    assert all(f"- {p.name}: {p.hint}" in seen["prompt"] for p in catalog())
