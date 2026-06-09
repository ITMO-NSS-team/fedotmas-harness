"""Programmatic combinators that compile authoring forms into an engine System.

A step is a plain async function returning a value. The combinator owns the fact tags,
the triggers, and the wiring. seq lays steps in a line by data dependency.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from fedotmas.adapters import as_agent
from fedotmas.engine.contract import Agent, Fact, Result, View
from fedotmas.engine.system import System

StepFn = Callable[[Any, View], Awaitable[Any]]


@dataclass
class Step:
    name: str
    fn: StepFn


def _as_step(item: Step | StepFn) -> Step:
    return (
        item
        if isinstance(item, Step)
        else Step(getattr(item, "__name__", "step"), item)
    )


def _step_agent(step: Step, reads: str, out: str) -> Agent:
    async def invoke(input: Any, view: View) -> Result:
        value = await step.fn(view.value(reads) if reads else None, view)
        return Result(writes=[Fact(tag=out, value=value)])

    return as_agent(invoke, name=step.name, reads=reads)


def seq(*items: Step | StepFn, entry: str, out: str) -> System:
    steps = [_as_step(i) for i in items]
    agents: list[Agent] = []
    prev = entry
    for i, step in enumerate(steps):
        out_tag = out if i == len(steps) - 1 else step.name
        agents.append(_step_agent(step, prev, out_tag))
        prev = out_tag
    return System(agents)
