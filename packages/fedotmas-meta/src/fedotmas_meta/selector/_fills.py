from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from typing import Any

from fedotmas_llm import agent
from pydantic import BaseModel, Field, create_model

from fedotmas_meta.menu import Cell, Fill

Fills = Callable[[Cell, str], Awaitable[Fill]]

PROMPT = (
    "You write the prompts for a coordination structure that a separate selector has "
    "already chosen. Read the task and the structure; give every role a prompt tailored "
    "to the task. Mapping roles take 2-4 named sub-agents keyed by short names, in "
    "execution order."
)

_MAPPING_ROLES = frozenset({"steps", "workers", "debaters"})


def fill_schema(cell: Cell) -> type[BaseModel]:
    """A pydantic model over the cell's roles: a prompt per role, sub-agents for mapping roles."""
    fields: dict[str, Any] = {
        role: (dict[str, str], Field(min_length=2, max_length=4))
        if role in _MAPPING_ROLES
        else (str, ...)
        for role in cell.roles
    }
    return create_model(f"Fill_{cell.name}", **fields)


def frozen(fills: Mapping[str, Fill]) -> Fills:
    """Fills fixed ahead of time, keyed by cell name; the task is ignored."""

    async def source(cell: Cell, task: str) -> Fill:
        return fills[cell.name]

    return source


def drafted(assembler: Any) -> Fills:
    """Fills written per task by the assembler model over the cell's fill schema."""

    async def source(cell: Cell, task: str) -> Fill:
        write = agent(
            "assembler",
            prompt=PROMPT,
            input=f"Task: {{task}}\nStructure: {cell.hint}\nRoles: {', '.join(cell.roles)}",
            takes=dict,
            returns=fill_schema(cell),
            llm=assembler,
        )
        run = await write.run({"task": task})
        if not run.ok:
            raise RuntimeError(f"fill for {cell.name!r} failed: {run.reason}")
        return run.value.model_dump()

    return source
