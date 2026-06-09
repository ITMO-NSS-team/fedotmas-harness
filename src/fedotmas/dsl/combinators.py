"""Programmatic combinators that compile authoring forms into an engine System.

A step is a plain async function returning a value. The combinator owns the fact tags,
the triggers, and the wiring. seq lays steps in a line by data dependency, parallel
fans out and joins, branch routes to one case by a label, loop iterates in rounds.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from fedotmas.adapters import as_agent
from fedotmas.engine.contract import Agent, Fact, Result, View
from fedotmas.engine.system import System

StepFn = Callable[[Any, View], Awaitable[Any]]
JoinFn = Callable[[list[Any], View], Awaitable[Any]]


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


def _join_agent(fn: JoinFn, prefix: str, out: str, width: int) -> Agent:
    async def invoke(input: Any, view: View) -> Result:
        values = [f.value for f in view.query(prefix)]
        value = await fn(values, view)
        return Result(writes=[Fact(tag=out, value=value)])

    return as_agent(
        invoke,
        name=f"join:{out}",
        reads=prefix,
        trigger=lambda v: v.count(prefix) == width,
    )


def parallel(*branches: Step | StepFn, join: JoinFn, entry: str, out: str) -> System:
    steps = [_as_step(b) for b in branches]
    agents: list[Agent] = [
        _step_agent(Step(f"{step.name}:{i}", step.fn), entry, f"{out}:{i}")
        for i, step in enumerate(steps)
    ]
    agents.append(_join_agent(join, f"{out}:*", out, len(steps)))
    return System(agents)


def _route_agent(select: StepFn, entry: str, label: str, out: str) -> Agent:
    async def invoke(input: Any, view: View) -> Result:
        value = await select(view.value(entry) if entry else None, view)
        return Result(writes=[Fact(tag=label, value=value)])

    return as_agent(invoke, name=f"route:{out}", reads=entry)


def _case_agent(case: str, step: Step, label: str, entry: str, out: str) -> Agent:
    async def invoke(input: Any, view: View) -> Result:
        value = await step.fn(view.value(entry) if entry else None, view)
        return Result(writes=[Fact(tag=out, value=value)])

    return as_agent(
        invoke, name=step.name, reads=label, trigger=lambda v: v.value(label) == case
    )


def branch(
    select: StepFn, *, cases: dict[str, Step | StepFn], entry: str, out: str
) -> System:
    label = f"{out}:route"
    agents: list[Agent] = [_route_agent(select, entry, label, out)]
    for case, item in cases.items():
        agents.append(_case_agent(case, _as_step(item), label, entry, out))
    return System(agents)


LoopUntil = Callable[[Any, View], bool]


def _latest(view: View, pattern: str) -> Fact | None:
    found = view.query(pattern)
    return found[-1] if found else None


def _loop_head(step: Step, gate: str, own: str, entry: str, until: LoopUntil) -> Agent:
    async def invoke(input: Any, view: View) -> Result:
        g = _latest(view, gate + "*")
        src = g.value if g is not None else view.value(entry)
        value = await step.fn(src, view)
        n = view.count(own + "*") + 1
        return Result(writes=[Fact(tag=own + str(n), value=value)])

    def trigger(view: View) -> bool:
        g = _latest(view, gate + "*")
        if g is None:
            return view.exists(entry)
        return not until(g.value, view)

    return as_agent(invoke, name=step.name, reads=gate + "*", trigger=trigger)


def _loop_step(step: Step, up: str, own: str) -> Agent:
    async def invoke(input: Any, view: View) -> Result:
        u = _latest(view, up + "*")
        value = await step.fn(u.value if u is not None else None, view)
        n = view.count(own + "*") + 1
        return Result(writes=[Fact(tag=own + str(n), value=value)])

    return as_agent(invoke, name=step.name, reads=up + "*")


def _loop_finalize(gate: str, head: str, out: str, until: LoopUntil) -> Agent:
    async def invoke(input: Any, view: View) -> Result:
        artifact = _latest(view, head + "*")
        value = artifact.value if artifact is not None else None
        return Result(writes=[Fact(tag=out, value=value)])

    def trigger(view: View) -> bool:
        g = _latest(view, gate + "*")
        return g is not None and until(g.value, view) and not view.exists(out)

    return as_agent(invoke, name=f"done:{out}", reads=gate + "*", trigger=trigger)


def loop(*items: Step | StepFn, until: LoopUntil, entry: str, out: str) -> System:
    steps = [_as_step(i) for i in items]
    pre = [f"{out}:{j}." for j in range(len(steps))]
    gate = pre[-1]
    agents: list[Agent] = [_loop_head(steps[0], gate, pre[0], entry, until)]
    for j in range(1, len(steps)):
        agents.append(_loop_step(steps[j], pre[j - 1], pre[j]))
    agents.append(_loop_finalize(gate, pre[0], out, until))
    return System(agents)
