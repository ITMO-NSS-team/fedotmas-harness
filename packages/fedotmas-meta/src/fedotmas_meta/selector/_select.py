"""Internal: the zero-shot pattern pick, itself one constrained sdk agent."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from fedotmas.sdk import LLM, agent

from fedotmas_meta.presets import Preset, catalog

_PROMPT = (
    "You design multi-agent systems. Pick the execution pattern that best fits"
    " the task you are given. Patterns:\n{menu}"
)


@dataclass(frozen=True)
class Selection:
    pattern: str


async def select(
    task: str, *, llm: LLM, presets: Sequence[Preset] | None = None
) -> Selection:
    """Match a task to a pattern family: one constrained choice over the catalog menu."""
    pool = tuple(presets) if presets is not None else catalog()
    menu = "\n".join(f"- {p.name}: {p.hint}" for p in pool)
    pick = agent(
        "select", prompt=_PROMPT.format(menu=menu), labels=[p.name for p in pool]
    )
    run = await pick.run(task, llm=llm)
    if not run.ok:
        raise RuntimeError(f"selection failed: {run.reason}")
    return Selection(pattern=run.value)
