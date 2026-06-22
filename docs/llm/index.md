# LLM extension

`fedotmas-llm` is the model-backed layer over the [core engine](../core/engine.md): the `agent` flow atom, the `PromptRule` blackboard rule, a one-method `LLM` seam, and a `PydanticAI` backend.
The core stays model-free, so everything that knows about a model lives here.

Install it with the bundled backend:

```
pip install fedotmas-llm[pydantic-ai]
```

The package re-exports three names, `agent`, `PromptRule`, and the `LLM` protocol; the backend ships under `fedotmas_llm.adapters.pydantic_ai`.

## The LLM seam

`agent` and `PromptRule` are agnostic about how a prompt turns into a value.
That seam is one protocol, a parameter you pass, never a way into the engine.

```python
class LLM(Protocol):
    async def complete(
        self, prompt: str, input: Any, view: View, returns: Any = str
    ) -> Any: ...
```

`returns` carries the declared output type of the node, so a backend that supports structured output can produce that type directly, while a plain text backend ignores it.
Anything with that method is a backend: a model client, a whole framework, a stub, a fake in a test.

## Binding a backend

The binding has two levels.
A node carries its own backend through `llm=` on the factory (`agent(..., llm=backend)` or `PromptRule(..., llm=backend)`), and a whole run gets a default through the run-scoped `bind` mapping under its `llm` key.

```python
run = await flow.run(value, bind={"llm": backend})              # default for every node
board_run = await board.run(seed, goal="out", bind={"llm": backend})
```

Per-node bindings win, so a flow can run one node on a different model and the rest on the default.
A model-backed node with no backend from either level fails at compile time, with its name in the message, never mid-run.

## The PydanticAI backend

`PydanticAI` wraps a [pydantic-ai](https://ai.pydantic.dev) agent as an `LLM`.
The constructor takes a model string and optional settings; a structured `returns` type is passed straight through, and token usage accumulates on `.usage`.

```python
from fedotmas_llm.adapters.pydantic_ai import PydanticAI

backend = PydanticAI("openai-responses:gpt-4o-mini")
run = await flow.run("tea", bind={"llm": backend})
print(backend.usage)        # {"input_tokens": ..., "output_tokens": ..., "requests": ...}
```

The model string is whatever pydantic-ai accepts, for example `openai-responses:gpt-4o-mini` or `openrouter:qwen/qwen3-30b`.
