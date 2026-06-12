# fedotmas

Agent systems generation and harness: a tiny orchestration engine plus a typed SDK on top.

```python
from fedotmas.sdk import agent
from fedotmas.adapters.pydantic_ai import PydanticAI

outline = agent("outline", prompt="Give a 3-bullet outline for the topic.")
draft = agent("draft", prompt="Write one vivid paragraph from the outline.")

run = await (outline + draft).run("heralt of rivia", llm=PydanticAI("openai-responses:gpt-4o-mini"))
print(run.value)
```

Docs: [sdk](docs/sdk.md) (start here), [engine](docs/engine.md) (under the hood). Examples: [examples/](examples/README.md).

Planned, not in the tree yet (placeholder packages removed until real):

- v0.1 - `dsl`: the spec language and compiler, wrappers for other frameworks and any agents and converting to dsl
- `meta` - the meta-agent: an application built on the SDK itself (designer -> wirer -> compile loop, the compiler as a deterministic critic). Generate / select / combine MAS as one synthesis spectrum over the spec: M0 generate a system from a task, M1 pattern library (the MAS patterns as spec templates, not DSL primitives), M2 select among cataloged systems by task description, M3 combine systems via spec-as-node composition. Grows as assets (templates, catalog, prompts), not engine features; engine/sdk/dsl never depend on it
- v0.2 - time across the run boundary, one contract in two parts: wave epochs for joins (fixes the pinned wave-skew limitation) and checkpoint-style resume/persistence (a resume seam on the executor plus a facts export; where the blobs live stays outside the framework)
- v0.2 - `reliability`: retries, fallback, routing?
