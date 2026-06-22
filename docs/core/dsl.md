# DSL

The DSL is the [flow surface](flow.md) as a JSON document, so a program (or a person) can emit a system instead of writing Python.
A manifest describes a pool of nodes and how they wire together; `compile` turns it into a `Flow` you run exactly like a hand-built one.

```python
from fedotmas import action
from fedotmas.dsl import compile, parse


@action
async def research(topic: str) -> str:
    return f"facts about {topic}"


@action
async def write(facts: str) -> str:
    return f"draft from {facts}"


doc = """
{
  "version": 1,
  "nodes": {
    "research": {"ref": "research"},
    "write": {"ref": "write"}
  },
  "flow": ["research", "write"]
}
"""

flow = compile(parse(doc), atoms={"research": research, "write": write})
run = await flow.run("tea")
```

## The document

A `Manifest` has three parts:

- `nodes`: the pool, a name to a node definition.
  A definition is a `{"ref": ...}` object (a registered code atom, filled from `atoms=` at compile), or a prompt node (a bare string, or a `{"prompt": ...}` object carrying `input`/`takes`/`returns`/`labels`) built by a `providers` entry supplied at compile.
- `flows`: optional named flows, spliced into the main flow by name.
  Node and flow names share one namespace.
- `flow`: the main wiring.
  Optional so a pool-only stage validates; `compile` requires it.

The flow wiring mirrors the SDK combinators:

| JSON form | SDK equivalent |
|-----------|----------------|
| `"name"` | a node or named-flow reference |
| `["a", "b", ...]` | sequence (`+`) |
| `{"gather": [...]}` | `gather` |
| `{"branch": "key", "cases": {...}}` | `branch` by a state key |
| `{"loop": <flow>, "until": "key" or <condition>}` | `.loop` |
| `{"nest": <flow>}` | `nest` |
| `{"step": <flow>, "into": "key"}` / `{"step": <flow>, "merge": true}` | `.into` / `.merge` |

Branch routes by a state key only (never by node name).
A loop's `until` is a state key (truthy) or a `Condition` over one key.
A `step` takes exactly one of `into` or `merge`.

## Compile

```python
def compile(
    manifest: Manifest,
    *,
    atoms: dict[str, Flow] | None = None,        # bodies for "ref" nodes
    types: dict[str, type] | None = None,        # named types for takes/returns
    providers: dict[str, Any] | None = None,     # node-kind builders for prompt nodes
) -> Flow: ...
```

Registries are compile parameters, not document content.
A `{"ref": "bump"}` node is filled from `atoms={"bump": action(bump)}`, a `takes`/`returns` naming a registered type is resolved from `types`, and a prompt node is built by `providers`, the seam an [extension provider](../llm/agents.md) fills.
The compile is deterministic and all-or-nothing: the same document gives the same `Flow`, and a single document compiles to a single graph or to nothing.

## Parse, validate, merge

`parse(text)` turns one JSON string into a validated `Manifest`.
A Python caller with a dict in hand uses `Manifest.model_validate` directly.
Validation is pydantic: the JSON value shape discriminates the form, so one defect reports one issue.

Every failure speaks one contract, a `ManifestError` carrying `Issue`s of `(path, message, expected)`.
This is the feedback fact of an emit-validate-retry loop: hand the issues back to the emitter and let it fix the document.

```python
from fedotmas.dsl import ManifestError, parse

try:
    manifest = parse(text)
except ManifestError as err:
    for issue in err.issues:
        print(issue.path, issue.message, issue.expected)
```

`merge(*parts)` overlays a staged emission deterministically: names union with a double definition as an error, at most one part carries the main flow, the first `meta` wins.
It lets an emitter produce the pool and the wiring in separate steps.

## Schema

The grammar ships as JSON Schema, the form you hand to an emitter:

- `manifest_schema()` is the schema of the whole language, for one-shot emission.
- `schema_for_flow(pool)` is the schema of a wiring stage closed over a known node pool, for the second step of a staged emission.

## Reference

| Import | What it is |
|--------|------------|
| `dsl.Manifest` | the document: `nodes`, `flows`, `flow`, `version`, optional `meta` |
| `dsl.parse` | JSON text to a validated `Manifest`, or `ManifestError` |
| `dsl.compile` | `Manifest` to a `Flow`; `atoms`, `types`, `providers` registries are parameters |
| `dsl.merge` | overlay staged parts into one manifest |
| `dsl.manifest_schema` / `dsl.schema_for_flow` | the grammar as JSON Schema |
| `dsl.ManifestError` / `dsl.Issue` | the failure contract: `(path, message, expected)` |
