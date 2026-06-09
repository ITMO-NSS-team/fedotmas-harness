# SDK

The SDK is the embedded Python surface for building agent systems by hand. Its primary surface
is the flow: a typed arrow from one value to another. `Flow[A, B]` is a piece of a multi-agent
system that takes an input of type `A` and produces an output of type `B`. You build small
arrows, compose them with a handful of operators, and the composition is itself an arrow you
can compose further.

Underneath, a flow is just a way to produce agents for the runtime. It carries no runtime of
its own. The point the SDK adds on top of the runtime is the types: because every arrow
declares what it consumes and what it yields, the composition is checkable before anything
runs. A stage that produces a pair feeding a stage that expects a single value is a type
error, not a surprise at step four.

## The mental model

State in the runtime lives in one shared store as a growing list of tagged facts. Agents
watch that store, declare when they are ready, run in synchronized rounds, and write new
facts back. A flow never asks you to think about any of that. You write plain typed
functions and stitch them with operators.

A flow is **lazy**. Building `a + b` allocates nothing. The arrow is a recipe. It turns into
real agents and real fact tags only when you call `.system(entry, out)`, which hands you the
bag of agents the runtime executes. The same flow can be compiled more than once, reused, or
nested inside a larger flow, because it bakes in no concrete tags until that moment.

So there are two languages in play. The arrow language (`+`, `*`, `gather`, `branch`,
`.loop`, `embed`) is what you write. The fact-and-agent language is what it compiles to. Most
of this page is the arrow language, with the compiled trace shown alongside so you can see the
seam; the atoms that fill the arrows and the rule surface for shapeless work come after.

## A first flow

An atom is a typed async function wrapped with `@action`. Sequence them with `+`. The output
type of each stage has to match the input type of the next, and that is the whole contract.

```python
import asyncio

from fedotmas.sdk import action
from fedotmas.engine.contract import Fact, View
from fedotmas.engine.executor import ReactiveExecutor
from fedotmas.engine.store import Store
from fedotmas.engine.terminate import Goal


@action
async def research(topic: str, view: View) -> str:
    return f"facts about {topic}"


@action
async def write(facts: str, view: View) -> str:
    return f"draft from {facts}"


@action
async def edit(draft: str, view: View) -> str:
    return f"edited {draft}"


async def main() -> None:
    chain = research + write + edit
    system = chain.system(entry="topic", out="final")
    store = Store()
    async for r in ReactiveExecutor().stream(
        system, store,
        seed=[Fact(tag="topic", value="haiku")],
        terminate=Goal(lambda v: v.exists("final")),
    ):
        print(f"step {r.step}: {r.fired} -> {[f.tag for f in r.writes]}")
    print("final:", store.snapshot().value("final"))
```

Output:

```
step 0: ['research#1'] -> ['research#1']
step 1: ['write#2'] -> ['write#2']
step 2: ['edit#3'] -> ['edit#3']
step 3: ['alias:final'] -> ['final']
final: edited draft from facts about haiku
```

The compiler gave each atom a fresh tag (`research#1`, `write#2`, `edit#3`) so the same atom
could appear twice in one flow without colliding. The last step is an `alias`: the flow built
its output under `edit#3`, you asked for it under `final`, so one extra agent copies the
value across. That alias is the only bookkeeping the boundary costs.

## Atoms

An atom is a leaf arrow, the smallest `Flow`. Three factories produce one, differing only in
what fills the leaf. All three return a `Flow[A, B]` and compose with the same operators.

### action

`action` lifts a python function. The body is the behavior.

```python
def action(fn: ActionFn[A, B]) -> Flow[A, B]: ...
```

The function has the signature `async (input: A, view: View) -> B`. The first argument is the
value flowing in, already unwrapped from its fact, typed as `A`. The return value, typed `B`,
becomes the arrow's output. `view` is the read-only snapshot of the whole store, there if a
stage needs to look at something beyond its direct input, ignorable otherwise. The types on the
signature are the types of the arrow, so write them honestly rather than reaching for `Any`:
`research` above is a `Flow[str, str]`, and that annotation is what makes the composition
checkable.

### agent

`agent` lifts a prompt. The behavior is data, not code, which is what lets an LLM node be
authored without hand-writing a model call.

```python
def agent(name, *, prompt, takes=str, returns=str, llm=None, role="") -> Flow[A, B]: ...
```

`takes` and `returns` declare the arrow's types, defaulting to `str -> str`, so an `agent`
composes under `ty` exactly like an `action`. The node does not bind a backend itself. At
runtime it calls an `LLM` (below), passed as `llm`, and that binding is injected, which keeps
the SDK agnostic about which backend runs.

```python
summarize = agent("summarize", prompt="Summarize in one word:", llm=some_llm)
chain = shout + summarize
```

Running `shout + summarize` on `"hello world"` with a model that returns the first word:

```
step 0: ['shout#1'] -> ['shout#1']
step 1: ['summarize#2'] -> ['summarize#2']
step 2: ['alias:out'] -> ['out']
out: HELLO
```

An `agent` is an atom like any other. It took its input from the previous stage and handed a
value to the next, and nothing in the composition knew or cared that the middle step was a
model call rather than a function.

### decision

`decision` lifts a prompt into a router. Its output is one label from a fixed set, so its type
is `Flow[A, str]`, and it is what drives a `branch` when the route is chosen at runtime rather
than by a plain function.

```python
def decision(name, *, prompt, labels, takes=str, llm=None, role="") -> Flow[A, str]: ...
```

The result is validated against `labels` at runtime. A `branch` accepts a `decision` in place
of a callable selector:

```python
route = decision("route", prompt="Pick the topic:", labels=["math", "prose"], llm=some_llm)
router = branch(route, {"math": solver, "prose": writer})
```

```
step 0: ['route#2'] -> ['route#2']
step 1: ['branch#1:route'] -> ['branch#1:in:math']
step 2: ['solve#3'] -> ['solve#3']
step 3: ['branch#1:join:math'] -> ['branch#1']
step 4: ['alias:answer'] -> ['answer']
answer: 2 + 2 = 4
```

The decision runs first and writes a label, the router sends the original input to the chosen
case, and exactly one case fires. A plain `Callable` selector still works and saves the extra
step; reach for `decision` when the choice itself needs a model.

### LLM

`agent` and `decision` are agnostic about how a prompt turns into a value. That seam is one
protocol, and it is a parameter of those factories, not a way into the engine.

```python
class LLM(Protocol):
    async def complete(
        self, prompt: str, input: Any, view: View, returns: type = str
    ) -> Any: ...
```

`returns` carries the declared output type of the node, so a backend that supports structured
output can produce that type directly; a plain text backend ignores it. Anything with that
method is a backend: an LLM client, a whole framework, a stub, a fake in a test. The SDK never
imports a provider. This is the LLM-agnostic point made concrete. An `action` is a model-free
atom, an `agent` is the same atom shape with an `LLM` behind it, and the two compose without
distinction.

## Sequence: `+`

`a + b` runs `a`, then feeds its output to `b`.

```python
def __add__(self, other: Flow[B, C]) -> Flow[A, C]: ...
```

Read the type: a `Flow[A, B]` plus a `Flow[B, C]` is a `Flow[A, C]`. The middle type `B` has
to line up, which is the entire safety claim. If you write `research + edit` where one yields
a draft and the other expects something else, the checker rejects the `+` itself, at the line
where you wrote it, before any run. `.then` is the spelled-out method behind the operator if
you prefer words to symbols.

## Parallel: `*`

`a * b` runs both arrows on the same input and pairs their outputs into a tuple.

```python
def __mul__(self, other: Flow[A, C]) -> Flow[A, tuple[B, C]]: ...
```

A `Flow[A, B]` times a `Flow[A, C]` is a `Flow[A, tuple[B, C]]`. Both sides read the same `A`,
the runtime runs them together, and the result is `(B, C)`. There is no separate join
operator. The join is an ordinary next stage that consumes the tuple.

```python
@action
async def upper(text: str, view: View) -> str:
    return text.upper()


@action
async def reverse(text: str, view: View) -> str:
    return text[::-1]


@action
async def combine(parts: tuple[str, str], view: View) -> str:
    return " | ".join(parts)


fanned = (upper * reverse) + combine
```

Output of running `fanned` on `"abc"`:

```
step 0: ['upper#1', 'reverse#2'] -> ['upper#1', 'reverse#2']
step 1: ['par#3'] -> ['par#3']
step 2: ['combine#4'] -> ['combine#4']
step 3: ['alias:result'] -> ['result']
result: ABC | cba
```

Both branches fire in step 0. The `par#3` agent in step 1 is the implicit pairing: it waits
for both branch outputs and writes the tuple. Then `combine` consumes it.

This is where the types earn their keep. `combine` is typed `tuple[str, str] -> str`. If you
forget the join and try to feed the product straight into a stage that wants a single string,
the type does not line up and the `+` is rejected. The unjoined parallel cannot slip through
as a runtime mistake, it shows up as a static one.

!!! note "Precedence does the right thing"
    `*` binds tighter than `+` in Python, so `a + b * c + d` groups as `a + (b * c) + d`. The
    parallel block clusters on its own without parentheses, which is usually what you mean.

## N-ary parallel: gather

`*` pairs exactly two arrows, nesting tuples if you chain it. When you want a variable number
of same-typed branches, `gather` is the n-ary form.

```python
def gather(*flows: Flow[A, B]) -> Flow[A, list[B]]: ...
```

It fans one input to every branch and collects the outputs into a `list[B]`. A reducer over
that list is, again, just the next stage.

```python
from collections import Counter

from fedotmas.sdk import action, gather


@action
async def solver_a(q: str, view: View) -> str:
    return "42"


# solver_b, solver_c likewise


@action
async def majority(answers: list[str], view: View) -> str:
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

All three solvers run together, `gather#1` collects the list, `majority` reduces it. This is
the shape that voting and mixture-of-agents want, and the `list[B]` output makes the reducer
mandatory by type: a bare `gather` is not yet a usable value, it is a list waiting for a fold.

## Branch

`branch` routes the input to exactly one of several cases, picked at runtime by a label.

```python
def branch(select: Callable[[A], str], cases: dict[str, Flow[A, B]]) -> Flow[A, B]: ...
```

`select` looks at the input and returns a key. Only the case under that key is fed an input
fact, so only its sub-flow runs, and every case converges to the one branch output. Each case
is a full `Flow[A, B]`, which means a case can itself be a chain, a parallel block, or another
branch.

```python
from fedotmas.sdk import action, branch


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

The `route` agent wrote the input to `branch#1:in:math` and nowhere else, so only the `math`
case fired. The `prose` and `code` cases never woke up, because their input facts were never
written. Each case ends in a uniquely named `join` agent that copies its result to the shared
output, which is how three cases can share one output tag without colliding.

!!! note "Cases should agree on their output type"
    A flow's strongest guarantees come from `+` and `.loop`, where the type checker forces the
    stitch. `branch` is a step looser. The cases dictionary makes the checker widen `B` to the
    common supertype of the cases rather than rejecting a mismatch outright, so heterogeneous
    case outputs are not caught as crisply. The boundary is typed and the intended use
    (cases that all produce the same `B`) is clean. Keep the cases homogeneous and the arrow
    behaves like the rest.

## Loop

`.loop` iterates an arrow, threading its output back as its next input, until a predicate
clears.

```python
def loop(self: Flow[A, A], until: Callable[[A], bool]) -> Flow[A, A]: ...
```

The signature has a sharp edge worth reading. The receiver is typed `self: Flow[A, A]`, an
arrow whose input and output are the same type. You can only call `.loop` on a
state-preserving flow, because a loop has to feed each round's output into the next round, and
that is only coherent when the two types match. Try `.loop` on a `Flow[str, int]` and the
checker refuses: the state contract is enforced by the type, not by a comment.

```python
THRESHOLD = 3


@action
async def revise(draft: dict, view: View) -> dict:
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

Each round, the `iter` agent runs the body once over the latest state and writes a versioned
state fact (`loop#1:s:1`, then `:2`, then `:3`). The versioning is what lets one agent fire
again: every round consumes a genuinely new fact, so the runtime's fire-once rule sees fresh
input and allows the next turn. `until` reads the latest state and stops the iteration. Then
`done` publishes the final state under one stable tag.

The body runs as an isolated sub-system each round. Whatever the body is, a single action or a
whole `generate + critique` chain, it is compiled once and run to its own completion per turn,
so the loop does not care how complex one iteration is.

```python
@action
async def generate(prev: dict, view: View) -> dict:
    n = prev["n"] + 1
    return {"n": n, "quality": n}


@action
async def critique(draft: dict, view: View) -> dict:
    return {**draft, "approved": draft["quality"] >= THRESHOLD}


optimize = (generate + critique).loop(lambda s: s["approved"])
```

Reflection (one body action) and evaluator-optimizer (a two-stage body) are the same arrow.
The difference is entirely in what you put inside the loop, never in the loop itself.

## Embed

Not every part of a system is a tidy arrow. Some work is opportunistic: a set of rules that
fire whenever the store happens to satisfy them, in no fixed order, converging on a goal. That
is the rule surface, written with `Rule` and `blackboard`, and it does not have a single
`A -> B` shape to type. `embed` is how such a sub-system enters the arrow world as one node.

```python
def embed(
    target: System | Flow[A, B], *, entry: str, out: str, until: Terminate | None = None
) -> Flow[A, B]: ...
```

It wraps a whole sub-system. At runtime the node spins up its own inner store, seeds it with
the incoming value under `entry`, runs the sub-system to its goal (`until`, defaulting to "the
`out` fact exists"), and writes that one result outward. The boundary is typed, the interior
is opaque.

```python
from fedotmas.sdk import Flow, Rule, action, blackboard, embed

investigation = blackboard(
    Rule("hypothesizer",
         lambda v: v.exists("question") and not v.exists("hypothesis"),
         hypothesize, writes="hypothesis"),
    Rule("researcher",
         lambda v: v.exists("hypothesis") and not v.exists("evidence"),
         research, writes="evidence"),
    Rule("verifier",
         lambda v: v.exists("evidence") and not v.exists("conclusion"),
         verify, writes="conclusion"),
)

solve: Flow[str, str] = embed(investigation, entry="question", out="conclusion")

pipeline = frame + solve + report
```

Output:

```
step 0: ['frame#1'] -> ['frame#1']
step 1: ['embed#2'] -> ['embed#2']
step 2: ['report#3'] -> ['report#3']
step 3: ['alias:out'] -> ['out']
out: REPORT: X confirmed
```

From the outside, `embed#2` is a single step. The three-rule investigation ran to its
conclusion inside its own store and surfaced one fact. That is why `solve` drops into a plain
`frame + solve + report` chain as if it were an atom.

Two things about `embed`. First, it takes a `System` or a `Flow`, so it is also the primitive
for nesting one flow inside another as a self-contained unit, not only for absorbing a
blackboard. Second, because the wrapped target is a runtime `System` with no static type, the
checker cannot infer the boundary types. You annotate them yourself
(`solve: Flow[str, str] = embed(...)`), and that annotation is load-bearing: it is what the
checker uses to verify the stitch on either side. Feed a `str` into a flow built around a
`Flow[tuple[str, str], str]` embed and the mismatch is caught.

## Why the types

Everything above leans on one idea. The runtime values are `Any` at execution time; the types
live only at design time, checked by `ty` (or mypy) before you run. They buy correctness by
construction. An unjoined parallel is a `tuple` the next stage must consume, a forgotten
reducer is a `list` with nowhere to go, a loop over a non-state-preserving body is a receiver
that does not match `Flow[A, A]`. Each of these is a static error at the line you wrote,
rather than a wrong fact discovered mid-run.

The payoff scales past hand-written systems. A typed Python arrow algebra is a small, prunable
search space and a far better target for a program that generates systems than a freeform
diagram. The same property that catches your mistake prunes a generator's.

## The rule surface

Not every system is an arrow. When activation is opportunistic, when agents fire in no fixed
order as the store happens to satisfy them, there is no `A -> B` shape to type. For that the SDK
has a second surface: rules.

A `Rule` pairs an author-written condition with a step. Unlike a flow there is no topology to
derive a trigger from, so you write `when` yourself; the helper owns the fact bookkeeping.

```python
@dataclass
class Rule:
    name: str
    when: Callable[[View], bool]
    fn: Callable[[Any, View], Awaitable[Any]]
    writes: str
    reads: str = ""


def blackboard(*rules: Rule) -> System: ...
```

`blackboard` collects rules into a runnable `System`, the same kind a flow compiles to.

```python
from fedotmas.sdk import Rule, blackboard

investigation = blackboard(
    Rule("hypothesizer",
         lambda v: v.exists("question") and not v.exists("hypothesis"),
         hypothesize, writes="hypothesis"),
    Rule("researcher",
         lambda v: v.exists("hypothesis") and not v.exists("evidence"),
         research, writes="evidence"),
    Rule("verifier",
         lambda v: v.exists("evidence") and not v.exists("conclusion"),
         verify, writes="conclusion"),
)
```

```
step 0: ['hypothesizer'] -> ['hypothesis']
step 1: ['researcher'] -> ['evidence']
step 2: ['verifier'] -> ['conclusion']
conclusion: X confirmed
```

Each rule woke on its own condition, in an order nobody declared. The order fell out of the
facts, only with the fact bookkeeping handled for you. Inside a blackboard there are no arrow
types and so no static check; that is the price of an open shape, and the reason to keep
blackboards for work that genuinely has no fixed topology. To use a goal-terminating blackboard
as one node in a flow, wrap it with `embed`.

## When a flow is the wrong shape

A flow is the right tool when the topology is known when you write it: a chain, a fan-out, a
router, a refinement loop. It is the dataflow subset of what the runtime can do, and within
that subset it gives you static checking the raw runtime cannot.

Some systems do not have a fixed topology. The width is decided at runtime, the next speaker is
chosen by a manager, work is handed off dynamically, a task is auctioned to the best bidder.
Those are not arrows. They live on the rule surface (authored triggers, optionally a runtime
policy that picks who fires), where there is no shape to derive and so nothing to type. Forcing
them into an arrow would be a category error. When such a system does converge on a goal,
`embed` brings its result back across the boundary as a single typed node. Reach for a flow
where the shape is fixed, reach for rules where order is emergent, and let `embed` be the seam
between them.

## Reference

| Import                       | What it is                                                   |
|------------------------------|--------------------------------------------------------------|
| `sdk.Flow`                   | the typed arrow `Flow[A, B]`, a lazy dataflow fragment        |
| `sdk.action`                 | wrap a typed async function as a mechanical atom              |
| `sdk.agent`                  | lift a prompt into an LLM atom, `Flow[A, B]` over an `LLM`    |
| `sdk.decision`               | lift a prompt into a router, `Flow[A, str]` over labels       |
| `sdk.LLM`                    | the LLM seam, one async `complete(prompt, input, view, returns)` |
| `Flow.__add__` / `.then`     | sequence, `Flow[A, B] + Flow[B, C] -> Flow[A, C]`             |
| `Flow.__mul__` / `.par`      | parallel product, `-> Flow[A, tuple[B, C]]`                   |
| `sdk.gather`                 | n-ary parallel, `*Flow[A, B] -> Flow[A, list[B]]`            |
| `sdk.branch`                 | route to one case by a label, `-> Flow[A, B]`                |
| `Flow.loop`                  | iterate a state-preserving flow, `Flow[A, A] -> Flow[A, A]`   |
| `sdk.embed`                  | run a whole sub-system as one typed node                     |
| `Flow.system`                | compile to a runnable `System`, given `entry` and `out` tags |
| `sdk.Rule`                   | a condition plus a step, the unit of the rule surface         |
| `sdk.blackboard`             | collect rules into a runnable `System`                        |

Things to keep in mind:

- A flow is lazy. It allocates agents and tags only at `.system(entry, out)`, so it is free to
  reuse and nest.
- An atom is a function (`action`) or a prompt over an `LLM` (`agent`, `decision`). Both are
  the same `Flow` and compose alike, and the SDK never imports an LLM provider.
- The types are a design-time contract. They are checked before the run and are `Any` at
  runtime, which is why the function signatures should be honest.
- `+` and `.loop` enforce their stitch crisply. `branch` is looser, keep its cases homogeneous.
- The join is never a special operator. A `*` product or a `gather` list is consumed by an
  ordinary next stage, and the type makes that consumption mandatory.
- Use a flow where the topology is fixed. Use rules where order is emergent, and `embed` to
  carry an emergent sub-system back into the arrow world.
```
