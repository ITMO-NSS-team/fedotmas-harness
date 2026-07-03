from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from fedotmas import Flow, action
from fedotmas_llm import agent

from fedotmas_meta._menu import MENU, Cell, Fill, cell_for
from fedotmas_meta._recipe import Recipe

PROMPT = (
    "You pick the coordination structure a task will be solved with, before any solving "
    "starts. Read the task, the executor card and the menu of structures; answer with the "
    "recipe coordinates of the structure to run. Coordination multiplies token cost, so "
    "buy structure only where the executor would likely fail alone."
)


def menu_card() -> str:
    """The menu as selector input: one line per cell, coordinates and hint, no names."""
    return "\n".join(
        f"- {json.dumps(c.recipe.model_dump())}  {c.hint}" for c in MENU.values()
    )


def resolve(recipe: Recipe) -> Cell:
    """The menu cell for a recipe, falling back to single for off-menu points."""
    try:
        return cell_for(recipe)
    except LookupError:
        return MENU["single"]


def _intake(card: str) -> Flow[str, dict]:
    @action
    async def prepare(task: str) -> dict:
        return {"task": task, "executor": card, "menu": menu_card()}

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


def emit_recipe(selector: Any, card: str) -> Flow[str, Recipe]:
    """Emission alone: task in, Recipe out."""
    return _intake(card) + _picker(selector)


def select_pipeline(
    *,
    selector: Any,
    executor: Any,
    fills: Mapping[str, Fill],
    card: str = "a small language model",
    budget: int = 60,
) -> Flow[str, str]:
    """Emit a recipe, compile it from the menu, run the built system on the executor."""

    @action
    async def execute(state: dict) -> str:
        recipe: Recipe = state["recipe"]
        cell = resolve(recipe)
        flow = cell.build(fills[cell.name], recipe)
        out = await flow.run(state["task"], bind={"llm": executor}, budget=budget)
        if not out.ok:
            raise RuntimeError(f"cell {cell.name!r} failed: {out.reason}")
        return out.value

    return _intake(card) + _picker(selector).into("recipe") + execute
