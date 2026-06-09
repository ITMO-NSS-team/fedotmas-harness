"""The rule surface: a thin blackboard helper, peer to the flow arrows.

A Rule pairs an author-written condition with a step. Unlike a flow there is no topology to
derive a trigger from, so the author writes `when` directly; the helper only owns the
Result/Fact boilerplate. This is the blackboard superset that the edge-shaped arrows cannot
express (opportunistic, non-linear activation).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from fedotmas.adapters import as_agent
from fedotmas.engine.contract import Agent, Fact, Result, View
from fedotmas.engine.system import System

StepFn = Callable[[Any, View], Awaitable[Any]]
When = Callable[[View], bool]


@dataclass
class Rule:
    """One blackboard agent. When `when(view)` holds, run `fn` and write its result to the
    `writes` fact; `reads` names the fact fed to fn as input (empty means none). The author
    writes `when` directly because there is no topology to derive a trigger from.
    """

    name: str
    when: When
    fn: StepFn
    writes: str
    reads: str = ""


def _rule_agent(rule: Rule) -> Agent:
    async def invoke(input: Any, view: View) -> Result:
        value = await rule.fn(view.value(rule.reads) if rule.reads else None, view)
        return Result(writes=[Fact(tag=rule.writes, value=value)])

    return as_agent(invoke, name=rule.name, reads=rule.reads, trigger=rule.when)


def blackboard(*rules: Rule) -> System:
    """Assemble rules into a blackboard System: agents that self-activate when their `when`
    condition holds, with no fixed topology. Run it directly on the engine, or wrap it with
    embed to drop the whole blackboard into a flow as one typed node.
    """
    return System([_rule_agent(r) for r in rules])
