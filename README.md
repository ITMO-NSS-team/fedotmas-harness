<div align="center">

# `FEDOT.MAS`

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-3776ab.svg)](https://python.org)

</div>

> [!WARNING]
> Early development (v0.1). The API will change between versions.

An agent-SDK-agnostic framework for building multi-agent systems: a tiny orchestration engine, a typed SDK on top, and a JSON manifest language so systems can be written as data.

## Install

Not yet on PyPI, install from git with [uv](https://docs.astral.sh/uv/):

```bash
git clone https://github.com/ITMO-NSS-team/fedotmas.git
cd fedotmas
uv sync --all-packages
```

The LLM examples need a provider key, e.g. `OPENAI_API_KEY`.

```python
import asyncio

from fedotmas.sdk import agent
from fedotmas_llm.adapters.pydantic_ai import PydanticAI

outline = agent("outline", prompt="Give a 3-bullet outline for the topic.")
draft = agent("draft", prompt="Write one vivid paragraph from the outline.")


async def main():
    run = await (outline + draft).run("heralt of rivia", llm=PydanticAI("openai-responses:gpt-4o-mini"))
    print(run.value)


asyncio.run(main())
```

LLM and plain code are the same kind of node:

```python
from fedotmas.sdk import action, agent

@action
async def count(text: str, view) -> dict:
    return {"text": text, "words": len(text.split())}

flow = agent("summarize", prompt="Summarize in one sentence.") + count
```

Any agent SDK binds the same way: the `LLM` seam is a single method, see [backends.py](examples/sdk-llm/backends.py).

The same system as a document:

```python
from fedotmas import dsl

flow = dsl.compile(dsl.parse("""{
  "version": 1,
  "nodes": {"outline": "Give a 3-bullet outline for the topic.",
            "draft": "Write one vivid paragraph from the outline."},
  "flow": ["outline", "draft"]
}"""))
```

## Packages

- [`fedotmas`](packages/fedotmas): the core engine, sdk, dsl
- [`fedotmas-llm`](packages/fedotmas-llm): the LLM layer over the engine with provider backends and serving; early
- [`fedotmas-meta`](packages/fedotmas-meta): the meta-agent that builds systems from task descriptions; early

## Planned

- meta-agent M0: match a task to a pattern family, fill the roles, compile; the compiler acts as a deterministic critic
- serving: run a manifest over HTTP/SSE and MCP (`fedotmas-llm`); MCP, file/URI, and A2A capabilities wired by reference
- v0.2: wave epochs for joins, checkpoint-style resume/persistence
- reliability: a middleware seam plus retry/fallback combinators
- richer runtime memory (knowledge graphs) behind a store port
