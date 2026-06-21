"""Public extension surface for custom node-kinds and rule-kinds.

A node-kind is a Flow subclass that implements `_build(ctx, entry)`: read run-scoped bindings
off `ctx.bindings` (e.g. a backend under "llm"), mint unique tags with `ctx.fresh`, and wrap an
`async (input, view) -> value` body with `node_from_fn`. A rule-kind is a Rule subclass that
overrides `_body(bind)` (and `_validate`) to build its blackboard step from the same bindings.
The LLM extension's agent and PromptRule are built exactly this way; A2A/file/MCP kinds plug in
through the same seam.
"""

from __future__ import annotations

from fedotmas.sdk.atoms import node_from_fn
from fedotmas.sdk.blackboard import Rule
from fedotmas.sdk.flow._algebra import Flow
from fedotmas.sdk.flow._nodes import Ctx

__all__ = ["Ctx", "Flow", "Rule", "node_from_fn"]
