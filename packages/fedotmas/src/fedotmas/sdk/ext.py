"""Public extension surface for custom node-kinds (cartridges).

A node-kind is a Flow subclass that implements `_build(ctx, entry)`: read run-scoped bindings
off `ctx.bindings` (e.g. a backend under "llm"), mint unique tags with `ctx.fresh`, and wrap an
`async (input, view) -> value` body with `node_from_fn`. The LLM cartridge's agent is built
exactly this way; A2A/file/MCP node-kinds plug in through the same seam.
"""

from __future__ import annotations

from fedotmas.sdk.atoms import node_from_fn
from fedotmas.sdk.flow._algebra import Flow
from fedotmas.sdk.flow._nodes import Ctx

__all__ = ["Ctx", "Flow", "node_from_fn"]
