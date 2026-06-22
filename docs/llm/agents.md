# Agents and rules

The flow surface fills its arrows with `action` and the blackboard fills its rules with code.
`fedotmas-llm` adds the model-backed counterparts: `agent` for a flow atom and `PromptRule` for a blackboard rule.

## agent

`agent` lifts a prompt into a `Flow[A, B]`, an atom that composes with `+`, `gather`, `branch`, and the rest exactly like an `action`.

```python
def agent(
    name, *, prompt, input=None, takes=str, returns=str, labels=None, llm=None,
) -> Flow[A, B]: ...
```

`prompt` is the static system prompt.
`takes` and `returns` declare the arrow's types, defaulting to `str -> str`, so an `agent` type-checks under `ty` exactly like an `action`.
`llm` binds the backend per node, or it comes from the run-scoped `bind` (see [the seam](index.md#binding-a-backend)).

```python
from fedotmas_llm import agent

summarize = agent("summarize", prompt="Summarize in one word:", llm=backend)
chain = shout + summarize
```

Nothing in the composition knows or cares that the middle step is a model call rather than a function.

## agent over state

A loop, a swarm, or a chat threads a *state* dict through every node: each node reads part of it, calls the model, and folds the reply back in.
The reading side is the `input` keyword, a template for what the model sees, rendered over the node's input (dict keys or model fields by name, store tags as a fallback, `{input}` for the whole value; a typo fails the node with the missing key named).
The writing side is `.into`/`.merge`, the [core state combinators](../core/flow.md#state-threading-into-and-merge); declare `takes=dict` so the agent takes the state.

```python
from pydantic import BaseModel


class Handoff(BaseModel):
    reply: str
    station: str            # constrain with Literal[...] to keep handoffs on the rails


triage = agent(
    "triage",
    prompt="You are front-line triage. Reply, and set station to who acts next.",
    input="{ticket}",        # the model sees the ticket, not the whole state dict
    takes=dict,
    returns=Handoff,
).merge()                    # state | {"reply": ..., "station": ...}
```

The model saw one field, the reply chose the next station, and the whole node is still data.

## agent as a classifier: labels

`labels` constrains an agent's output to one label from a finite set, making it a `Flow[A, str]` router: the shape that drives a `branch` when the route is chosen by the model rather than by data already in the state.

```python
route = agent("route", prompt="Pick the topic:", labels=["math", "prose"], llm=backend)
router = branch(route, {"math": solver, "prose": writer})
```

The label set rides to the backend as a `Literal` in `returns`, so a structured backend cannot produce anything outside it, and the reply is validated against `labels` regardless.
A plain `Callable` selector still works and saves the extra step; reach for `labels` when the choice itself needs a model.
It does not combine with `returns` (the label set is the return type); to land the label in a dict state, e.g. a group-chat manager writing who speaks next, compose `agent(..., labels=[...], takes=dict).into("speaker")`.

## PromptRule

`PromptRule` is the [blackboard](../core/blackboard.md) rule whose body is a prompt, the reactive counterpart of `agent` to `action`.
It subclasses the core `Rule`, adding `prompt`/`input`/`returns`/`llm`, and `reads`/`writes`/`when`/`meta` behave exactly as on a code rule.

```python
from fedotmas import blackboard
from fedotmas_llm import PromptRule

investigation = blackboard(
    PromptRule("hypothesizer", reads="question",  writes="hypothesis", prompt="Propose one testable hypothesis."),
    PromptRule("researcher",   reads="hypothesis", writes="evidence",  prompt="State one supporting piece of evidence."),
    PromptRule("verifier",     reads="evidence",   writes="conclusion", prompt="Weigh and conclude in one line."),
)

run = await investigation.run({"question": "what is it?"}, goal="conclusion", bind={"llm": backend})
```

A board is model-free and takes no backend itself; the `llm` rides on each `PromptRule` or on the run-scoped `bind`.
