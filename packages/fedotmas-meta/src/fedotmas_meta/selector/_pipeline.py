from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from fedotmas import Flow, RunError, action
from fedotmas_llm import agent

from fedotmas_meta.menu import MENU, Cell, Recipe, menu_card, resolve
from fedotmas_meta.selector._fills import Fills

PROMPT = (
    "You pick the coordination structure a task will be solved with, before any solving "
    "starts. Read the task, the executor card and the menu of structures; answer with the "
    "recipe coordinates of the structure to run. Coordination multiplies token cost, so "
    "buy structure only where the executor would likely fail alone."
)


def _intake(card: str, menu: Mapping[str, Cell]) -> Flow[str, dict]:
    lines = menu_card(menu)

    @action
    async def prepare(task: str) -> dict:
        return {"task": task, "executor": card, "menu": lines}

    return prepare


def _picker(selector: Any) -> Flow[dict, Recipe]:
    return agent(
        "selector",
        prompt=PROMPT,
        input="Task: {task}\nExecutor: {executor}\nMenu:\n{menu}",
        takes=dict,
        returns=Recipe,
        llm=selector,
    )


def emit_recipe(
    selector: Any, card: str, menu: Mapping[str, Cell] = MENU
) -> Flow[str, Recipe]:
    """Emission alone: task in, Recipe out."""
    return _intake(card, menu) + _picker(selector)


def pipeline(
    *,
    selector: Any,
    executor: Any,
    fills: Fills,
    card: str = "a small language model",
    budget: int = 60,
    menu: Mapping[str, Cell] = MENU,
) -> Flow[str, str]:
    """Emit a recipe, source the fill, compile from the menu, run on the executor."""

    @action
    async def execute(state: dict) -> str:
        recipe: Recipe = state["recipe"]
        cell = resolve(recipe, menu)
        fill = await fills(cell, state["task"])
        out = await cell.build(fill, recipe).run(
            state["task"], bind={"llm": executor}, budget=budget
        )
        try:
            return out.unwrap()
        except RunError as e:
            raise RunError(f"cell {cell.name!r}: {e}") from None

    return _intake(card, menu) + _picker(selector).into("recipe") + execute
