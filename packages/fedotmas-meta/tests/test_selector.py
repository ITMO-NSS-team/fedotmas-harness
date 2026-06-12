"""The selector: a constrained pick over the catalog menu."""

from typing import Any

from fedotmas.engine import View
from fedotmas_meta.presets import catalog, get
from fedotmas_meta.selector import select


class FakeLLM:
    def __init__(self, reply) -> None:
        self._reply = reply

    async def complete(
        self, prompt: str, input: Any, view: View, returns: Any = str
    ) -> Any:
        return self._reply(prompt, input)


async def test_select_returns_a_catalog_pattern():
    picked = await select("handle tickets", llm=FakeLLM(lambda p, i: "router"))
    assert picked.pattern == "router"
    assert get(picked.pattern).roles


async def test_select_menu_lists_every_hint():
    seen = {}

    def reply(p, i):
        seen["prompt"] = p
        return "single"

    await select("t", llm=FakeLLM(reply))
    assert all(f"- {p.name}: {p.hint}" in seen["prompt"] for p in catalog())


async def test_select_narrows_to_a_given_pool():
    pool = [get("single"), get("chain")]
    seen = {}

    def reply(p, i):
        seen["prompt"] = p
        return "chain"

    picked = await select("t", llm=FakeLLM(reply), presets=pool)
    assert picked.pattern == "chain"
    assert "debate" not in seen["prompt"]
