"""The SDK: the embedded Python surface for building agent systems by hand.

Two surfaces over one engine. Typed Flow arrows (flow) for fixed-topology dataflow, and the
rule/blackboard surface (rules) for emergent activation. Both compile to an engine System.
"""

from fedotmas.sdk.flow import (
    Flow,
    Model,
    action,
    agent,
    branch,
    decision,
    embed,
    gather,
)
from fedotmas.sdk.rules import Rule, blackboard

__all__ = [
    "Flow",
    "Model",
    "Rule",
    "action",
    "agent",
    "blackboard",
    "branch",
    "decision",
    "embed",
    "gather",
]
