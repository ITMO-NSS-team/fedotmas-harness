"""The dsl: the serialized form of the arrow surface, a language a program can emit.

A manifest is a JSON document describing a system: a pool of nodes (inline prompts or
references to registered atoms), optional named flows, and the main flow wiring them with
the sdk combinators — seq, gather, branch, loop, nest, step. The document is a pydantic
tree: parse validates, compile turns it into a Flow (one document, one graph, no partial
success), and every failure speaks one contract — a ManifestError of (path, message,
expected) issues, the feedback fact of an emit-validate-retry loop. The grammar ships as
JSON Schema: manifest_schema for the whole language, schema_for_flow for a wiring stage
closed over a known pool; merge overlays the parts of a staged emission.
"""

from fedotmas.dsl._compile import compile
from fedotmas.dsl._errors import Issue, ManifestError
from fedotmas.dsl._manifest import (
    AtomRef,
    Branch,
    Condition,
    FlowExpr,
    Gather,
    Loop,
    Manifest,
    ManifestRef,
    Meta,
    Nest,
    NodeDef,
    Prompted,
    Step,
    merge,
    parse,
)
from fedotmas.dsl._schema import manifest_schema, schema_for_flow

__all__ = [
    "AtomRef",
    "Branch",
    "Condition",
    "FlowExpr",
    "Gather",
    "Issue",
    "Loop",
    "Manifest",
    "ManifestError",
    "ManifestRef",
    "Meta",
    "Nest",
    "NodeDef",
    "Prompted",
    "Step",
    "compile",
    "manifest_schema",
    "merge",
    "parse",
    "schema_for_flow",
]
