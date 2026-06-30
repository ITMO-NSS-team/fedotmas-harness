from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from fedotmas_llm import LLM, agent

from fedotmas_meta.presets import Preset

_PROMPT = (
    "You design multi-agent systems. Pick the execution pattern that best fits"
    " the task you are given. Patterns:\n{menu}"
)


@dataclass(frozen=True)
class Selection:
    pattern: str


async def select(task: str, *, presets: Sequence[Preset], llm: LLM) -> Selection:
    """Match a task to a pattern family: one constrained choice over the caller's menu."""
    pool = tuple(presets)
    menu = "\n".join(f"- {p.name}: {p.hint}" for p in pool)
    pick = agent(
        "select", prompt=_PROMPT.format(menu=menu), labels=[p.name for p in pool]
    )
    run = await pick.run(task, bind={"llm": llm})
    if not run.ok:
        raise RuntimeError(f"selection failed: {run.reason}")
    return Selection(pattern=run.value)
