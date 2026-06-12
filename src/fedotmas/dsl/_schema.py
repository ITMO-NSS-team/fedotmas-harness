"""Internal: the JSON Schema exports — the grammar handed to an emitting model."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from pydantic import TypeAdapter

from fedotmas.dsl._manifest import FlowExpr, Manifest


def manifest_schema() -> dict[str, Any]:
    """The schema of the whole language, for one-shot emission."""
    return Manifest.model_json_schema()


def schema_for_flow(pool: Iterable[str]) -> dict[str, Any]:
    """The wiring-stage schema: a flow expression whose bare-name production is closed to
    an enum of `pool`, so constrained decoding cannot reference an unknown node. Other
    strings (branch keys, condition keys) stay open."""
    names = sorted(set(pool))
    if not names:
        raise ValueError("schema_for_flow needs a non-empty pool")
    schema = TypeAdapter(FlowExpr).json_schema()
    union = schema["$defs"]["FlowExpr"]["oneOf"]
    union[union.index({"type": "string"})] = {"enum": names}
    return schema
