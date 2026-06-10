"""The blackboard surface: a thin helper for opportunistic, non-topological activation.

This is a peer of the flow arrows, not sugar over them: it expresses what arrows cannot, agents
that self-activate whenever the shared store satisfies their condition, in no order anyone wired.
A Rule pairs that condition with a step. For the common produce-once shape the condition is
derived from reads and writes, so a linear rule needs no trigger; write `when` only when the
activation is genuinely opportunistic (several rules contending on the same fact, conditions not
reducible to a single read).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from fedotmas.adapters import as_agent
from fedotmas.engine.contract import Agent, Fact, Result, View
from fedotmas.engine.system import System

StepFn = Callable[[Any, View], Awaitable[Any]]
When = Callable[[View], bool]


@dataclass
class Rule:
    """One blackboard agent. When its condition holds, run `fn` and write the result to the
    `writes` fact; `reads` names the fact fed to fn as input (empty means none). `when` defaults
    to produce-once, fire when `reads` exists and `writes` does not yet, so a pipeline rule needs
    no trigger; supply `when` for opportunistic activation. `meta` rides along to the agent, e.g.
    an auction bid that a Policy reads back off `agent.describe().meta`.
    """

    name: str
    fn: StepFn
    writes: str
    reads: str = ""
    when: When | None = None
    meta: dict[str, Any] = field(default_factory=dict)


def _produce_once(reads: str, writes: str) -> When:
    if reads:
        return lambda v: v.exists(reads) and not v.exists(writes)
    return lambda v: not v.exists(writes)


def _rule_agent(rule: Rule) -> Agent:
    async def invoke(input: Any, view: View) -> Result:
        value = await rule.fn(view.value(rule.reads) if rule.reads else None, view)
        return Result(writes=[Fact(tag=rule.writes, value=value)])

    trigger = rule.when or _produce_once(rule.reads, rule.writes)
    return as_agent(
        invoke, name=rule.name, reads=rule.reads, trigger=trigger, meta=rule.meta
    )


def blackboard(*rules: Rule) -> System:
    """Assemble rules into a blackboard System: agents that self-activate when their condition
    holds, with no fixed topology. Run it directly on the engine, or wrap it with nest to drop
    the whole blackboard into a flow as one typed node.
    """
    return System([_rule_agent(r) for r in rules])
