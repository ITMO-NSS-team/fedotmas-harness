"""The SDK: the embedded Python surface for building agent systems by hand.

Two surfaces over one engine. Typed Flow arrows (flow) for fixed-topology dataflow, and the
rule/blackboard surface (rules) for emergent activation, both model-free. The LLM atoms
(agent, decision) and the LLM seam live in llm; they are the only model-aware part. Every
surface compiles to an engine System.
"""

from fedotmas.sdk.flow import Flow, action, branch, embed, gather
from fedotmas.sdk.llm import LLM, agent, decision
from fedotmas.sdk.rules import Rule, blackboard

__all__ = [
    "LLM",
    "Flow",
    "Rule",
    "action",
    "agent",
    "blackboard",
    "branch",
    "decision",
    "embed",
    "gather",
]
