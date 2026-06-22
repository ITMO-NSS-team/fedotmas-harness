# fedotmas

The core engine and a typed SDK. A generic state machine with **no LLM vocabulary** and a single dependency (`pydantic`). Model-specific code lives in an extension like [`fedotmas-llm`](../fedotmas-llm); this package is what it builds on.

The unit is an **atom**: a typed async step that reads an input and writes an output. Lift any function with `action`, then compose. A pure-code system binds nothing, so `run` takes only the input.

## Flows

```python
import asyncio
from fedotmas import action, gather

@action
async def research(topic: str) -> str:
    return f"facts about {topic}"

@action
async def write(facts: str) -> str:
    return f"draft from {facts}"

@action
async def upper(text: str) -> str:
    return text.upper()

@action
async def reverse(text: str) -> str:
    return text[::-1]

chain = research + write         # sequence: write consumes research's output
fanned = gather(upper, reverse)  # run both on the same input, collect a list

print(asyncio.run(chain.run("haiku")).value)   # draft from facts about haiku
print(asyncio.run(fanned.run("abc")).value)    # ['ABC', 'cba']
```

`+` sequences, `gather` fans out, `branch` routes by label, `.loop` iterates, `nest` wraps a sub-system as one node. The type parameters check each join: `a + b` composes only when `b` accepts what `a` produces.

## Loops over a state

The same combinators express optimization. Feed each round's output back in until a goal holds:

```python
from fedotmas import action

TARGET = 100

@action
async def evolve(state: dict) -> dict:
    # one generation: improve the best candidate carried in the state
    return {"best": min(state["best"] + 7, TARGET), "gen": state["gen"] + 1}

search = evolve.loop(until=lambda s: s["best"] >= TARGET)
print(asyncio.run(search.run({"best": 0, "gen": 0})).value)   # {'best': 100, 'gen': 15}
```

Nothing here is agent-specific. A population of graphs, a simulation, a solver: if it moves a state toward a goal, it is a flow.

## Blackboard

When there is no fixed pipeline, declare **rules** that fire when their inputs appear:

```python
from fedotmas import Rule, blackboard

async def score(draft, view):
    return len(draft.split())

async def gate(n, view):
    return "ship" if n >= 5 else "revise"

board = blackboard(
    Rule(name="score", reads="draft", writes="score", fn=score),
    Rule(name="gate",  reads="score", writes="verdict", fn=gate),
)
print(asyncio.run(board.run({"draft": "a quick brown fox jumps"}, goal="verdict")).value)  # ship
```

Flow and blackboard are two views of one store. `nest` drops a goal-terminating board into a flow as one node.

## Extending the engine

A new node kind is a `Flow` subclass that implements `_build`. A new blackboard rule kind subclasses `Rule` and overrides `_body`. Both read run-scoped bindings off the context, so an extension can inject a backend the core never names. That is how [`fedotmas-llm`](../fedotmas-llm) adds `agent` and `PromptRule`. The surface is `fedotmas.ext`.
