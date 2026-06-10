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
- v0.2 - `reliability`: retries, fallback, routing?
- v0.2 - `memory`: runtime and persistence memory
