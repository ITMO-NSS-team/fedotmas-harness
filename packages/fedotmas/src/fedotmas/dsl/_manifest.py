"""Internal: the manifest models — the language as data — plus parse and merge.

The JSON value type discriminates the flow forms: a string is a name reference, a list is
the sequence, an object picks its combinator by characteristic key. No parser of its own:
validation is pydantic, the grammar is the JSON Schema export.
"""

from __future__ import annotations

import json
from typing import Annotated, Any, Literal

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Discriminator,
    Field,
    Tag,
    ValidationError,
    model_validator,
)
from typing_extensions import TypeAliasType

from fedotmas.dsl._errors import Issue, ManifestError, _from_validation_error
from fedotmas.sdk.flow import Condition as _SdkCondition

_Scalar = str | int | float | bool | None


def _field_key(name: str) -> str:
    if name.startswith("model_"):
        raise ValueError("pydantic reserves the model_ prefix")
    return name


_FieldKey = Annotated[
    str, Field(pattern=r"^[a-zA-Z][a-zA-Z0-9_]*$"), AfterValidator(_field_key)
]
_FieldName = Literal["str", "int", "float", "bool"]
FieldType = _FieldName | Annotated[list[_FieldName], Field(min_length=1, max_length=1)]


# Every union discriminates explicitly by value shape, so one defect reports one issue.
# Tags wear a "~" marker so the error translation can drop them from document paths.
def _type_tag(v: object) -> str:
    return "~fields" if isinstance(v, dict) else "~name"


TypeRef = Annotated[
    Annotated[str, Tag("~name")]
    | Annotated[dict[_FieldKey, FieldType], Tag("~fields")],
    Discriminator(_type_tag),
]


def _flow_tag(v: object) -> str | None:
    if isinstance(v, str):
        return "~ref"
    if isinstance(v, list):
        return "~seq"
    for key in ("gather", "branch", "loop", "nest", "step"):
        if key in v if isinstance(v, dict) else hasattr(v, key):
            return f"~{key}"
    return None


_flow_form = Discriminator(
    _flow_tag,
    custom_error_type="flow_expr",
    custom_error_message="not a flow expression: a name, a list, or a gather/branch/loop/nest/step object",
)
FlowExpr = TypeAliasType(
    "FlowExpr",
    """Annotated[
        Annotated[str, Tag('~ref')]
        | Annotated[list[FlowExpr], Field(min_length=1), Tag('~seq')]
        | Annotated[Gather, Tag('~gather')]
        | Annotated[Branch, Tag('~branch')]
        | Annotated[Loop, Tag('~loop')]
        | Annotated[Nest, Tag('~nest')]
        | Annotated[Step, Tag('~step')],
        _flow_form,
    ]""",
)


class Condition(_SdkCondition):
    """The sdk Condition with `value` narrowed to JSON scalars for a closed schema."""

    model_config = ConfigDict(extra="forbid")

    value: _Scalar = None


class _Form(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Gather(_Form):
    """N-ary parallel on one input; the output is the list of results in branch order."""

    gather: list[FlowExpr] = Field(min_length=1)


class Branch(_Form):
    """Route to one case by a state key (never by node name)."""

    branch: str
    cases: dict[str, FlowExpr]

    @model_validator(mode="after")
    def _has_cases(self) -> Branch:
        if not self.cases:
            raise ValueError("branch needs at least one case")
        return self


def _until_tag(v: object) -> str:
    return "~key" if isinstance(v, str) else "~cond"


class Loop(_Form):
    """Iterate the body until the condition clears: a state key (truthy) or a Condition.
    `budget` caps the supersteps inside one round; omitted means the sdk default."""

    loop: FlowExpr
    until: Annotated[
        Annotated[str, Tag("~key")] | Annotated[Condition, Tag("~cond")],
        Discriminator(_until_tag),
    ]
    budget: Annotated[int, Field(ge=1)] | None = None


class ManifestRef(_Form):
    """Reserved: a node running another manifest. In the schema now; rejected by the v1
    compiler."""

    manifest: str


def _nest_tag(v: object) -> str:
    inner = "manifest" in v if isinstance(v, dict) else isinstance(v, ManifestRef)
    return "~manifest" if inner else "~flow"


class Nest(_Form):
    """Run the inner flow as one opaque node with its own store; a bare flow name splices
    into the same store instead."""

    nest: Annotated[
        Annotated[FlowExpr, Tag("~flow")] | Annotated[ManifestRef, Tag("~manifest")],
        Discriminator(_nest_tag),
    ]
    budget: Annotated[int, Field(ge=1)] | None = None


class Step(_Form):
    """State-threading wrapper: `into` puts the output under one key of the dict state,
    `merge: true` folds a structured output's fields in. Exactly one of the two."""

    step: FlowExpr
    into: str | None = None
    merge: bool = False

    @model_validator(mode="after")
    def _into_xor_merge(self) -> Step:
        if (self.into is None) == (not self.merge):
            raise ValueError("step takes exactly one of into= or merge=true")
        return self


class Prompted(_Form):
    """An inline agent: takes/returns are a registered type name or inline flat fields;
    `labels` makes it a classifier and excludes returns."""

    prompt: str
    input: str | None = None
    takes: TypeRef | None = None
    returns: TypeRef | None = None
    labels: list[str] | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def _labels_fix_returns(self) -> Prompted:
        if self.labels is not None and self.returns is not None:
            raise ValueError(
                "labels fixes the output; it does not combine with returns"
            )
        return self


class AtomRef(_Form):
    """A registered atom: the node's body is python, supplied via compile's atoms registry."""

    ref: str


def _node_tag(v: object) -> str:
    if isinstance(v, str):
        return "~prompt"
    if "ref" in v if isinstance(v, dict) else isinstance(v, AtomRef):
        return "~atom"
    return "~agent"


NodeDef = Annotated[
    Annotated[str, Tag("~prompt")]
    | Annotated[Prompted, Tag("~agent")]
    | Annotated[AtomRef, Tag("~atom")],
    Discriminator(_node_tag),
]


class Meta(_Form):
    """Catalog identity of the manifest (the selection-milestone seam)."""

    name: str | None = None
    description: str | None = None
    intent: str | None = None


class Manifest(_Form):
    """One document: the node pool, the named flows, the main flow. Node and flow names
    share one namespace; `flow` is optional so a pool-only stage validates, compile
    requires it. Registries (atoms, types) are compile parameters, not document content."""

    version: Literal[1]
    meta: Meta | None = None
    nodes: dict[str, NodeDef] = Field(default_factory=dict)
    flows: dict[str, FlowExpr] = Field(default_factory=dict)
    flow: FlowExpr | None = None

    @model_validator(mode="after")
    def _one_namespace(self) -> Manifest:
        shared = sorted(self.nodes.keys() & self.flows.keys())
        if shared:
            raise ValueError(
                f"nodes and flows share one namespace; defined in both: {shared}"
            )
        return self


def parse(text: str) -> Manifest:
    """One JSON text -> one validated Manifest, or a ManifestError; never a partial
    document. A python caller with a dict in hand uses Manifest.model_validate directly."""
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as err:
        raise ManifestError(
            [Issue(path="<document>", message=str(err), expected="valid JSON")]
        ) from err
    if not isinstance(raw, dict):
        raise ManifestError(
            [
                Issue(
                    path="<document>",
                    message=f"a manifest is an object, got {type(raw).__name__}",
                    expected="an object with version, nodes, flow",
                )
            ]
        )
    try:
        return Manifest.model_validate(raw)
    except ValidationError as err:
        raise _from_validation_error(err) from err


def merge(*parts: Manifest) -> Manifest:
    """Deterministic overlay of a staged emission (pool first, wiring second): names union
    with a double definition as an error, at most one part carries the main flow, the
    first meta wins."""
    if not parts:
        raise ValueError("merge needs at least one manifest")
    issues: list[Issue] = []
    nodes: dict[str, Any] = {}
    flows: dict[str, Any] = {}
    flow: Any = None
    meta: Meta | None = None
    for part in parts:
        for section, mine, theirs in (
            ("nodes", nodes, part.nodes),
            ("flows", flows, part.flows),
        ):
            for name, value in theirs.items():
                if name in mine:
                    issues.append(
                        Issue(
                            path=f"{section}.{name}",
                            message="defined by more than one part",
                        )
                    )
                else:
                    mine[name] = value
        if part.flow is not None:
            if flow is not None:
                issues.append(
                    Issue(
                        path="flow", message="more than one part carries the main flow"
                    )
                )
            else:
                flow = part.flow
        meta = meta or part.meta
    if issues:
        raise ManifestError(issues)
    try:
        return Manifest(version=1, meta=meta, nodes=nodes, flows=flows, flow=flow)
    except ValidationError as err:
        raise _from_validation_error(err) from err
