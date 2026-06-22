# Flow surface

The SDK is the embedded Python surface for building agent systems by hand.
Its primary surface is the flow: a typed arrow from one value to another.
`Flow[A, B]` is a piece of a multi-agent system that takes an input of type `A` and produces an output of type `B`.
You build small arrows, compose them with a handful of operators, and the composition is itself an arrow you can compose further.

Underneath, a flow is just a way to produce nodes for the runtime.
It carries no runtime of its own.
The point the SDK adds on top of the runtime is the types: because every arrow declares what it consumes and what it yields, the composition is checkable before anything runs.
A stage that produces a pair feeding a stage that expects a single value is a type error, not a surprise at step four.

## The mental model

See [Concepts](concepts.md) for the shared model (store, facts, supersteps) and how the flow surface relates to the blackboard.
This page is the flow surface itself: the atoms, the operators, and the compiled trace beside each.

## A first flow

An atom is a typed async function wrapped with `@action`.
Sequence them with `+`.
The output type of each stage has to match the input type of the next, and that is the whole contract.

```python
import asyncio

from fedotmas import action


@action
async def research(topic: str) -> str:
    return f"facts about {topic}"


@action
async def write(facts: str) -> str:
    return f"draft from {facts}"


@action
async def edit(draft: str) -> str:
    return f"edited {draft}"


async def main() -> None:
    chain = research + write + edit
    run = await chain.run("haiku")
    for r in run.steps:
        print(f"step {r.step}: {r.fired} -> {[f.tag for f in r.writes]}")
    print("final:", run.value)
```

Output:

```
step 0: ['research#1'] -> ['research#1']
step 1: ['write#2'] -> ['write#2']
step 2: ['edit#3'] -> ['edit#3']
step 3: ['alias:out'] -> ['out']
final: edited draft from facts about haiku
```

The compiler gave each atom a fresh tag (`research#1`, `write#2`, `edit#3`) so the same atom could appear twice in one flow without colliding.
The last step is an `alias`: the flow built its output under `edit#3`, the runner reads it under `out`, so one extra node copies the value across.
That alias is the only bookkeeping the boundary costs.

## Running a flow

`run(value, *, bind=None, budget=100, policy=None, halt_on_error=True)` compiles the flow, seeds the input, executes to "the output exists" (capped by `budget` supersteps; the default 100 is a runaway guard for loops that never satisfy their `until`, pass `budget=None` to lift it), and returns an `Outcome`:

```python
run.value    # the produced output, or None if the run never got there
run.ok       # finished and produced the output
run.reason   # "goal" | "error" | "budget" | "stalled"
run.errors   # error facts from failed nodes, [] when clean
run.steps    # the full StepReport trace
run.view     # the final snapshot
run.unwrap() # the value, or raise RunError if the run did not finish clean
```

`reason` is worth reading on every failure.
`"error"` means a node failed and `errors` names it with its message.
`"budget"` means the step cap fired first, the usual suspect being a loop that never satisfied its `until`.
`"stalled"` means the system went quiet without producing the output, which is almost always a wiring gap.
A failing node never surfaces as a raw traceback out of `run`; it comes back as data on the `Outcome` (the full traceback rides in the error fact's `meta["traceback"]` when you need it).
By default the run stops at the first failed node; `halt_on_error=False` lets the rest of the system keep going, so the run can still reach `reason="goal"` with `errors` non-empty, and `ok` stays False either way.

`stream(value, ...)` is the same call as an async iterator of `StepReport`, for watching the run unfold live.
The `bind` mapping carries run-scoped values handed to every node, for configuration supplied at run time rather than baked into the flow.

When you need to own the store, the seed facts, or the terminate condition, drop to the explicit seam: `.system(entry, out)` compiles the flow to an engine `System`, and you hand it to a `ReactiveExecutor` yourself (see the [engine page](engine.md)).
`run` is that same path with everything derivable derived.

## Atoms

An atom is a leaf arrow, the smallest `Flow`.
`action` lifts a python function into one; the engine's universal unit is the `Node`, and the atom compiles to a node.
It returns a `Flow[A, B]` and composes with the operators below.

### action

`action` lifts a python function.
The body is the behavior.

```python
# ActionFn[A, B] = Callable[[A], Awaitable[B]] | Callable[[A, View], Awaitable[B]]
def action(fn: ActionFn[A, B], *, name: str | None = None) -> Flow[A, B]: ...
```

The function has the signature `async (input: A) -> B`, or `async (input: A, view: View) -> B` when it needs the store.
The first argument is the value flowing in, already unwrapped from its fact, typed as `A`.
The return value, typed `B`, becomes the arrow's output.
`view` is the read-only snapshot of the whole store, there if a stage needs to look at something beyond its direct input; the trailing argument is optional and supplied only when you declare it, so a body that ignores the store just omits it.
The types on the signature are the types of the arrow, so write them honestly rather than reaching for `Any`: `research` above is a `Flow[str, str]`, and that annotation is what makes the composition checkable.
`name` overrides the function's `__name__` in traces and error tags; pass it when lifting a lambda.

### State threading: into and merge

A stateless chain passes one value forward, but a loop threads a *state* dict through every node: each stage reads part of it and folds its result back in.
The folding is composition, not a parameter, and the two combinators work on any flow:

- `.into("key")` puts the flow's output under that key of the state and passes the rest through.
- `.merge()` overlays a structured output's fields onto the state.
  The output decides which keys change.

Both return `Flow[dict, dict]`, the state-preserving shape `.loop` wants; the flow under them takes the state, so its input type is `dict`.

```python
@action
async def tally(state: dict) -> int:
    return state["a"] + state["b"]


@action
async def bump(state: dict) -> dict:
    return {"n": state["n"] + 1}        # a partial patch


scored = tally.into("sum")    # {"a": 1, "b": 2} -> {"a": 1, "b": 2, "sum": 3}
patched = bump.merge()        # {"n": 1, "k": "x"} -> {"n": 2, "k": "x"}
```

`.into` lands a whole output under one key; `.merge` overlays a partial result, leaving the other keys untouched.
Both keep the `Flow[dict, dict]` shape that `.loop` and a state-key `branch` build on.

## Sequence: `+`

`a + b` runs `a`, then feeds its output to `b`.

```python
def __add__(self, other: Flow[B, C]) -> Flow[A, C]: ...
```

Read the type: a `Flow[A, B]` plus a `Flow[B, C]` is a `Flow[A, C]`.
The middle type `B` has to line up, which is the entire safety claim.
If you write `research + edit` where one yields a draft and the other expects something else, the checker rejects the `+` itself, at the line where you wrote it, before any run.

## Parallel: gather

`gather(a, b, ...)` runs several arrows on the same input and collects their outputs into a list.
It is the only parallel combinator; there is no binary product operator.

```python
def gather(*flows: Flow[A, B]) -> Flow[A, list[B]]: ...
```

A handful of `Flow[A, B]` become a `Flow[A, list[B]]`.
Every branch reads the same `A`, the runtime runs them together, and the result is the list of their outputs in branch order.
There is no separate join operator.
The join is an ordinary next stage that consumes the list.

```python
from collections import Counter

from fedotmas import action, gather


@action
async def solver_a(q: str) -> str:
    return "42"


# solver_b, solver_c likewise


@action
async def majority(answers: list[str]) -> str:
    return Counter(answers).most_common(1)[0][0]


vote = gather(solver_a, solver_b, solver_c) + majority
```

Output:

```
step 0: ['solver_a#2', 'solver_b#3', 'solver_c#4'] -> ['solver_a#2', 'solver_b#3', 'solver_c#4']
step 1: ['gather#1'] -> ['gather#1']
step 2: ['majority#5'] -> ['majority#5']
step 3: ['alias:answer'] -> ['answer']
answer: 42
```

All three solvers run together, `gather#1` collects the list, `majority` reduces it.
This is the shape that voting and mixture-of-agents want, and the `list[B]` output makes the reducer mandatory by type: a bare `gather` is not yet a usable value, it is a list waiting for a fold.

## Branch

`branch` routes the input to exactly one of several cases, picked at runtime by a label.

```python
def branch(
    select: Callable[[A], str] | Callable[[A, View], str] | str | Flow[A, str],
    cases: dict[str, Flow[A, B]],
) -> Flow[A, B]: ...
```

`select` picks the key: a callable over the input (optionally over the input and the view), a state key (`branch("station", ...)` routes by `state["station"]`, the declarative form), or a `Flow[A, str]` that computes the label.
Only the case under that key is fed an input fact, so only its sub-flow runs, and every case converges to the one branch output.
A label outside `cases` fails the route node with the label and the case set in the message.
Each case is a full `Flow[A, B]`, which means a case can itself be a chain, a parallel block, or another branch.

```python
from fedotmas import action, branch


def classify(q: str) -> str:
    if q[0].isdigit():
        return "math"
    if q.endswith("?"):
        return "prose"
    return "code"


router = branch(classify, {"math": solve, "prose": write, "code": code})
```

Running it on `"2 + 2"`:

```
step 0: ['branch#1:route'] -> ['branch#1:in:math']
step 1: ['solve#2'] -> ['solve#2']
step 2: ['branch#1:join:math'] -> ['branch#1']
step 3: ['alias:answer'] -> ['answer']
answer: 2 + 2 = 4
```

The route node wrote the input to `branch#1:in:math` and nowhere else, so only the `math` case fired.
The `prose` and `code` cases never woke up, because their input facts were never written.
Each case ends in a uniquely named `join` node that copies its result to the shared output, which is how three cases can share one output tag without colliding.

!!! note "Cases should agree on their output type"
    A flow's strongest guarantees come from `+` and `.loop`, where the type checker forces the stitch.
    `branch` is a step looser.
    The cases dictionary makes the checker widen `B` to the common supertype of the cases rather than rejecting a mismatch outright, so heterogeneous case outputs are not caught as crisply.
    The boundary is typed and the intended use (cases that all produce the same `B`) is clean.
    Keep the cases homogeneous and the arrow behaves like the rest.

## Loop

`.loop` iterates an arrow, threading its output back as its next input, until a predicate clears.

```python
def loop(
    self: Flow[A, A],
    until: Callable[[A], bool] | Callable[[A, View], bool] | Condition | str,
    *, budget: int | None = 100,
) -> Flow[A, A]: ...
```

`until` reads the state after each round: a callable (over the state, optionally the state and the view), a state key (`.loop(until="done")` stops when `state["done"]` is truthy), or a `Condition`, the declarative comparison (`Condition(key="rounds_left", op="lte", value=0)`) for conditions a bare key cannot say; the ordered ops (`gt`/`lt`/`gte`/`lte`) require a `value=` and a present key, the non-comparing ops (`truthy`/`not`/`exists`) reject a stray one, and both complain by name.
The key and Condition forms are data, which is what a program emitting a system can write.
Each round runs the body in its own inner store as one outer superstep, so the run's budget caps how many rounds happen, and `.loop`'s own `budget=` caps the supersteps inside one round (`None` lifts it).

The signature has a sharp edge worth reading.
The receiver is typed `self: Flow[A, A]`, an arrow whose input and output are the same type.
You can only call `.loop` on a state-preserving flow, because a loop has to feed each round's output into the next round, and that is only coherent when the two types match.
Try `.loop` on a `Flow[str, int]` and the checker refuses: the state contract is enforced by the type, not by a comment.

```python
THRESHOLD = 3


@action
async def revise(draft: dict) -> dict:
    n = draft["v"] + 1
    return {"v": n, "quality": n}


reflect = revise.loop(lambda s: s["quality"] >= THRESHOLD)
```

Output:

```
step 0: ['loop#1:iter'] -> ['loop#1:s:1']
step 1: ['loop#1:iter'] -> ['loop#1:s:2']
step 2: ['loop#1:iter'] -> ['loop#1:s:3']
step 3: ['loop#1:done'] -> ['loop#1']
step 4: ['alias:final'] -> ['final']
final: {'v': 3, 'quality': 3}
```

Each round, the `iter` node runs the body once over the latest state and writes a versioned state fact (`loop#1:s:1`, then `:2`, then `:3`).
The versioning is what lets one node fire again: every round consumes a genuinely new fact, so the runtime's fire-once rule sees fresh input and allows the next turn.
`until` reads the latest state and stops the iteration.
Then `done` publishes the final state under one stable tag.

The body runs as an isolated sub-system each round.
Whatever the body is, a single action or a whole `generate + critique` chain, it is compiled once and run to its own completion per turn, so the loop does not care how complex one iteration is.

```python
@action
async def generate(prev: dict) -> dict:
    n = prev["n"] + 1
    return {"n": n, "quality": n}


@action
async def critique(draft: dict) -> dict:
    return {**draft, "approved": draft["quality"] >= THRESHOLD}


optimize = (generate + critique).loop(lambda s: s["approved"])
```

Reflection (one body action) and evaluator-optimizer (a two-stage body) are the same arrow.
The difference is entirely in what you put inside the loop, never in the loop itself.

## Nest

Not every part of a system is a tidy arrow.
Some work is opportunistic: a set of rules that fire whenever the store happens to satisfy them, in no fixed order, converging on a goal.
That is the [blackboard surface](blackboard.md), written with `Rule` and `blackboard`, and it does not have a single `A -> B` shape to type.
`nest` is how such a sub-system enters the arrow world as one node.

```python
def nest(
    target: System | Flow[A, B] | Board, *, entry: str, out: str,
    until: Terminate | None = None, budget: int | None = 100,
) -> Flow[A, B]: ...
```

It wraps a whole sub-system.
At runtime the node spins up its own inner store, seeds it with the incoming value under `entry`, runs the sub-system to its goal (`until`, defaulting to "the `out` fact exists"), and writes that one result outward.
The boundary is typed, the interior is opaque.
The inner run is one superstep of the outer system, so the outer budget cannot interrupt it; `budget` caps the inner supersteps instead (`None` lifts it).
An inner failure halts the inner run and surfaces as this node's error fact.

```python
from fedotmas import Flow, Rule, action, blackboard, nest

investigation = blackboard(
    Rule("hypothesizer", hypothesize, writes="hypothesis", reads="question"),
    Rule("researcher",   research,    writes="evidence",   reads="hypothesis"),
    Rule("verifier",     verify,      writes="conclusion", reads="evidence"),
)

solve: Flow[str, str] = nest(investigation, entry="question", out="conclusion")

pipeline = frame + solve + report
```

Output:

```
step 0: ['frame#1'] -> ['frame#1']
step 1: ['nest#2'] -> ['nest#2']
step 2: ['report#3'] -> ['report#3']
step 3: ['alias:out'] -> ['out']
out: REPORT: X confirmed
```

From the outside, `nest#2` is a single step.
The three-rule investigation ran to its conclusion inside its own store and surfaced one fact.
That is why `solve` drops into a plain `frame + solve + report` chain as if it were an atom.

Two things about `nest`.
First, it takes a `Board`, a raw `System`, or a `Flow`, so it is also the primitive for nesting one flow inside another as a self-contained unit, not only for absorbing a blackboard; a `Flow` or `Board` target picks up the outer flow's run-scoped `bind` as its fallback backend, while a `System` is already compiled and keeps its own bindings.
Second, because the wrapped target has no static arrow type, the checker cannot infer the boundary types.
You annotate them yourself (`solve: Flow[str, str] = nest(...)`), and that annotation is load-bearing: it is what the checker uses to verify the stitch on either side.
Feed a `str` into a flow built around a `Flow[list[str], str]` nest and the mismatch is caught.

## Reference

| Import                       | What it is                                                   |
|------------------------------|--------------------------------------------------------------|
| `Flow`                       | the typed arrow `Flow[A, B]`, a lazy dataflow fragment        |
| `action`                     | wrap a typed async function as a mechanical atom              |
| `Condition`                  | a declarative predicate over one state key, for `.loop` (data, not code) |
| `Flow.__add__` (`+`)         | sequence, `Flow[A, B] + Flow[B, C] -> Flow[A, C]`             |
| `gather`                     | parallel, `*Flow[A, B] -> Flow[A, list[B]]`                  |
| `branch`                     | route to one case by a label: callable, state key, or a `Flow[A, str]` |
| `Flow.loop`                  | iterate a state-preserving flow until a callable, state key, or `Condition` clears; `budget=` caps one round |
| `Flow.into` / `Flow.merge`   | thread a dict state past a step: output under one key / structured output folded in |
| `nest`                       | run a whole sub-system (`Board`, `System`, or `Flow`) as one typed node; `budget=` caps its inner run |
| `Flow.system`                | compile to a runnable `System`, given `entry`/`out` tags and a default backend via `bind` |
| `Flow.run` / `Flow.stream`   | compile and execute on one input; returns `Outcome` / yields `StepReport` |
| `Outcome`                    | the outcome: `.value`, `.ok`, `.reason`, `.errors`, `.steps`, `.unwrap()` |
| `Outcome.unwrap` / `RunError` | return the value, or raise `RunError` if the run did not finish clean |

Everything above re-exports from the `fedotmas` package root.
Two authoring surfaces (`flow`, `blackboard`) are filled by `action` atoms, and the composition is checked by `ty` before anything runs.

Things to keep in mind:

- A flow is lazy.
  It allocates nodes and tags only at `.system(entry, out)` (or `.run`), so it is free to reuse and nest.
- An atom is a function wrapped with `action`, a `Flow` like any composite, composing with the same operators.
- State threading is declarative: `.into`/`.merge` fold a node's output back into a dict state, branch routes by a state key, loop stops on one.
- Failure is data.
  `Outcome.reason` distinguishes goal, error, budget, and stalled; `errors` names the failed node and its message, with the traceback in the fact's `meta`.
- The types are a design-time contract.
  They are checked before the run and are `Any` at runtime, which is why the function signatures should be honest.
- `+` and `.loop` enforce their stitch crisply. `branch` is looser, keep its cases homogeneous.
- The join is never a special operator.
  A `gather` list is consumed by an ordinary next stage, and the type makes that consumption mandatory.
