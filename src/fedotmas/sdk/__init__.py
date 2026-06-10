"""The SDK: the embedded Python surface for building agent systems by hand.

Two surfaces over one engine, plus the atoms that fill them. The flow arrows (flow) are for
fixed-topology dataflow; the blackboard (blackboard) is for emergent, condition-driven
activation. Both are filled by two kinds of leaf: action is code, agent is a prompt over the
LLM seam -- the word agent always means LLM-backed, the engine's universal unit is the Node.
Every surface compiles to an engine System. Application code imports these names flatly from
the package, e.g. `from fedotmas.sdk import agent, action, gather_all`; no name shadows a
stdlib import (the n-ary parallel is gather_all, not gather, to stay clear of
asyncio.gather). `from fedotmas import sdk` with the `sdk.` prefix also works if you prefer
explicit provenance.
"""

from fedotmas.sdk.atoms import LLM, action, agent
from fedotmas.sdk.blackboard import Board, Rule, blackboard, rule
from fedotmas.sdk.flow import Condition, Flow, FlowRun, branch, gather_all, nest

__all__ = [
    "LLM",
    "Board",
    "Condition",
    "Flow",
    "FlowRun",
    "Rule",
    "action",
    "agent",
    "blackboard",
    "branch",
    "gather_all",
    "nest",
    "rule",
]
