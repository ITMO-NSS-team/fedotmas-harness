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

- v0.1 - `dsl`: the spec language and compiler, wrappers for other frameworks and any agents and converting to dsl. `meta-agent` - selection pattern of a MAS by provided task features
- v0.2 - time across the run boundary, one contract in two parts: wave epochs for joins (fixes the pinned wave-skew limitation) and checkpoint-style resume/persistence (a resume seam on the executor plus a facts export; where the blobs live stays outside the framework)
- v0.2 - `reliability`: retries, fallback, routing?
