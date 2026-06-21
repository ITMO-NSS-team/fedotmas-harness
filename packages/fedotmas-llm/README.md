# fedotmas-llm

The LLM extension over the [`fedotmas`](../fedotmas) engine. A prompt becomes an atom, a backend binds at run time, and the whole flow, blackboard, and DSL surface carries over unchanged. It is built on the core's public extension surface, so the engine itself stays model-free.

The bundled backend ships under an extra: `pip install fedotmas-llm[pydantic-ai]`. Serving lives under `serve`.

> The runnable examples need a provider key, e.g. `OPENAI_API_KEY`.

## Agents

`agent` lifts a prompt into a typed atom, the LLM version of `action`. It composes with everything in the core:

```python
import asyncio
from fedotmas_llm import agent
from fedotmas_llm.adapters.pydantic_ai import PydanticAI

outline = agent("outline", prompt="Give a 3-bullet outline for the topic.")
draft = agent("draft", prompt="Write one vivid paragraph from the outline.")

flow = outline + draft
backend = PydanticAI("openai:gpt-4o-mini")
print(asyncio.run(flow.run("geralt of rivia", bind={"llm": backend})).value)
```

The backend binds once per run under `"llm"`, so nothing is hard-wired into the nodes. Code and prompts mix freely, because `action` and `agent` are the same kind of node:

```python
from fedotmas import action

@action
async def count(text: str) -> dict:
    return {"text": text, "words": len(text.split())}

flow = agent("summarize", prompt="Summarize in one sentence.") + count
```

## The backend seam

A backend is anything with one method: `complete(prompt, input, view, returns) -> value`. Any agent SDK plugs in, and the engine never imports a provider:

```python
class Echo:
    async def complete(self, prompt, input, view, returns=str):
        return f"{prompt}: {input}"

run = await flow.run("topic", bind={"llm": Echo()})
```

`PydanticAI` is the batteries-included adapter, with structured output and token accounting. See [examples/sdk-llm/backends.py](../../examples/sdk-llm/backends.py) for binding others.

## Classify and route

Give an agent `labels` and it returns one of them, the shape `branch` routes on:

```python
from fedotmas import branch

kind = agent("kind", prompt="Classify the issue.", labels=["bug", "feature"])
triage = branch(kind, {"bug": fix, "feature": plan})
```

## Reactive boards

`PromptRule` is the blackboard version, a rule whose body is a prompt. Code `Rule`s and `PromptRule`s share one board:

```python
from fedotmas import blackboard
from fedotmas_llm import PromptRule

board = blackboard(
    PromptRule(name="draft", reads="topic", writes="draft", prompt="Draft it."),
    PromptRule(name="check", reads="draft", writes="report", prompt="Review it."),
)
out = await board.run({"topic": "tea"}, goal="report", bind={"llm": backend})
```

## Systems as data (DSL)

A bare string node is a prompt. Pass the `agent` builder as the provider and the manifest compiles to the same flow:

```python
from fedotmas import dsl
from fedotmas_llm import agent

manifest = dsl.parse("""{
  "version": 1,
  "nodes": {"outline": "Give a 3-bullet outline for the topic.",
            "draft": "Write one vivid paragraph from the outline."},
  "flow": ["outline", "draft"]
}""")
flow = dsl.compile(manifest, providers={"agent": agent})
run = await flow.run("tea", bind={"llm": backend})
```

## Serving

Run a manifest over HTTP/SSE and MCP under the `serve` extra (`pip install fedotmas-llm[serve]`). MCP, file/URI, and A2A capabilities wire by reference. Early.
