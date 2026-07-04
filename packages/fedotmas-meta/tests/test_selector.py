"""The selector pipeline: emission, fill sources, compilation, off-menu fallback."""

from typing import Any

import pytest
from fedotmas_llm import Call
from fedotmas_meta import MENU, Recipe, Review
from fedotmas_meta.selector import drafted, emit_recipe, fill_schema, frozen, pipeline
from pydantic import ValidationError

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


class StubAssembler:
    async def complete(self, call: Call, view: Any) -> Any:
        return call.returns(
            **{
                name: f"you are the {name}"
                if field.annotation is str
                else {"first": f"{name} part one", "second": f"{name} part two"}
                for name, field in call.returns.model_fields.items()
            }
        )


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


async def test_frozen_fills_pipeline_runs_the_emitted_recipe():
    flow = pipeline(
        selector=StubSelector(Recipe(cooperate="shared")),
        executor=StubExecutor(),
        fills=frozen(FILLS),
    )
    run = await flow.run("what is 2 + 2?")
    assert run.ok, (run.reason, run.errors)
    assert isinstance(run.value, str) and run.value


async def test_off_menu_recipe_falls_back_to_single():
    flow = pipeline(
        selector=StubSelector(Recipe(decompose="master", verify="judge")),
        executor=StubExecutor(),
        fills=frozen(FILLS),
    )
    run = await flow.run("what is 2 + 2?")
    assert run.ok
    assert run.value.startswith("[solve]")


def test_fill_schema_mirrors_the_cell_roles():
    schema = fill_schema(MENU["orchestrator"])
    fields = schema.model_fields
    assert set(fields) == {"planner", "workers", "synthesizer"}
    assert fields["planner"].annotation is str
    fill = schema(
        planner="p", workers={"extract": "e", "compute": "c"}, synthesizer="s"
    )
    assert fill.model_dump()["workers"] == {"extract": "e", "compute": "c"}


def test_fill_schema_bounds_mapping_roles():
    schema = fill_schema(MENU["chain"])
    with pytest.raises(ValidationError):
        schema(steps={"only": "one step"})


def test_fill_schema_rejects_unsafe_sub_agent_names():
    schema = fill_schema(MENU["chain"])
    with pytest.raises(ValidationError):
        schema(steps={"data extraction": "e", "solve": "s"})


def test_fill_schema_rejects_names_shadowing_roles():
    schema = fill_schema(MENU["orchestrator_blackboard"])
    with pytest.raises(ValidationError, match="shadow"):
        schema(
            planner="p",
            workers={"skeptic": "e", "compute": "c"},
            skeptic="k",
            synthesizer="s",
        )


async def test_frozen_names_the_missing_cell():
    with pytest.raises(LookupError, match="no frozen fill for cell 'debate'"):
        await frozen(FILLS)(MENU["debate"], "task")


async def test_drafted_source_fills_the_cell_roles():
    cell = MENU["debate"]
    fill = await drafted(StubAssembler())(cell, "what is 2 + 2?")
    assert set(fill) == set(cell.roles)
    assert list(fill["debaters"]) == ["first", "second"]


async def test_pipeline_takes_a_caller_menu():
    menu = {"single": MENU["single"]}
    flow = pipeline(
        selector=StubSelector(Recipe(cooperate="shared")),
        executor=StubExecutor(),
        fills=frozen(FILLS),
        menu=menu,
    )
    run = await flow.run("what is 2 + 2?")
    assert run.ok
    assert run.value.startswith("[solve]")


@pytest.mark.parametrize("name", sorted(MENU))
async def test_every_cell_drafts_and_runs(name: str):
    flow = pipeline(
        selector=StubSelector(MENU[name].recipe),
        executor=StubExecutor(),
        fills=drafted(StubAssembler()),
    )
    run = await flow.run("what is 2 + 2?")
    assert run.ok, (run.reason, run.errors)
    assert isinstance(run.value, str) and run.value
