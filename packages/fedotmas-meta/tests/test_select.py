"""The select pipeline: emission, compilation, execution, off-menu fallback."""

from typing import Any

from fedotmas_llm import Call
from fedotmas_meta import Recipe, Review, emit_recipe, select_pipeline
from fedotmas_meta._select import menu_card, resolve

FILLS = {
    "single": {"agent": "solve"},
    "blackboard": {
        "researcher": "facts",
        "skeptic": "check",
        "synthesizer": "conclude",
    },
    "self_consistency": {"solver": "solve"},
}


class StubSelector:
    def __init__(self, recipe: Recipe) -> None:
        self.recipe = recipe

    async def complete(self, call: Call, view: Any) -> Any:
        return self.recipe


class StubExecutor:
    async def complete(self, call: Call, view: Any) -> Any:
        if call.returns is Review:
            return Review(approved=True, feedback="ok")
        return f"[{call.prompt}] {str(call.input)[:40]}"


async def test_emit_recipe_returns_coordinates():
    flow = emit_recipe(StubSelector(Recipe(width=3)), "weak 8b model")
    run = await flow.run("what is 2 + 2?")
    assert run.ok
    assert run.value == Recipe(width=3)


async def test_pipeline_compiles_and_executes_the_emitted_recipe():
    flow = select_pipeline(
        selector=StubSelector(Recipe(cooperate="shared")),
        executor=StubExecutor(),
        fills=FILLS,
    )
    run = await flow.run("what is 2 + 2?")
    assert run.ok, (run.reason, run.errors)
    assert isinstance(run.value, str) and run.value


async def test_off_menu_recipe_falls_back_to_single():
    off_menu = Recipe(decompose="master", verify="judge")
    assert resolve(off_menu).name == "single"
    flow = select_pipeline(
        selector=StubSelector(off_menu), executor=StubExecutor(), fills=FILLS
    )
    run = await flow.run("what is 2 + 2?")
    assert run.ok
    assert run.value.startswith("[solve]")


def test_menu_card_shows_coordinates_not_names():
    card = menu_card()
    assert len(card.splitlines()) == 9
    assert "single" not in card and "orchestrator" not in card
