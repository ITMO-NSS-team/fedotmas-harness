from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from typing import Annotated, Any

from fedotmas import RunError
from fedotmas_llm import agent
from pydantic import BaseModel, Field, StringConstraints, create_model, field_validator

from fedotmas_meta.menu import Cell, Fill

Fills = Callable[[Cell, str], Awaitable[Fill]]

PROMPT = (
    "You write the prompts for a coordination structure that a separate selector has "
    "already chosen. Read the task and the structure; give every role a prompt tailored "
    "to the task. Mapping roles take 2-4 named sub-agents keyed by short snake_case "
    "names, in execution order."
)

_Name = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]*$", max_length=30)]


def fill_schema(cell: Cell) -> type[BaseModel]:
    """A pydantic model over the cell's roles: a prompt per role, sub-agents for mapping
    roles, whose names are engine-safe and may not shadow the cell's other roles."""
    reserved = frozenset(cell.roles)

    def apart(cls: Any, v: dict[str, str]) -> dict[str, str]:
        if clash := reserved & v.keys():
            raise ValueError(f"sub-agent names shadow cell roles: {sorted(clash)}")
        return v

    fields: dict[str, Any] = {
        role: (dict[_Name, str], Field(min_length=2, max_length=4))
        if role in cell.many
        else (str, ...)
        for role in cell.roles
    }
    validators: dict[str, Any] = (
        {"_apart": field_validator(*cell.many)(apart)} if cell.many else {}
    )
    return create_model(f"Fill_{cell.name}", __validators__=validators, **fields)


def frozen(fills: Mapping[str, Fill]) -> Fills:
    """Fills fixed ahead of time, keyed by cell name; the task is ignored."""

    async def source(cell: Cell, task: str) -> Fill:
        if cell.name not in fills:
            raise LookupError(
                f"no frozen fill for cell {cell.name!r}; have: {sorted(fills)}"
            )
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
        try:
            return run.unwrap().model_dump()
        except RunError as e:
            raise RunError(f"fill for {cell.name!r}: {e}") from None

    return source
