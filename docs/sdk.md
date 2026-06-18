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

So there are two languages in play. The arrow language is what you write, and it comes in three
forms that follow the shape of each operation. One binary combinator is an infix operator, `+`
(sequence). Transforms of a flow you already have are methods: `.loop`,
`.into`, `.merge`. The rest build a flow from several flows or a whole system, so they are
plain functions: `gather` (parallel), `branch`, `nest`. The dividing line is simple: you
either do more to a flow you have (operator or method) or assemble a new one from parts
(function). The fact-and-agent language is what it compiles to. Most of this page is the arrow
language, with the compiled trace shown alongside so you can see the seam; the atoms that fill
the arrows and the blackboard surface for shapeless work come after.

## A first flow

An atom is a typed async function wrapped with `@action`. Sequence them with `+`. The output
type of each stage has to match the input type of the next, and that is the whole contract.

```python
import asyncio

from fedotmas.sdk import action


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

The compiler gave each atom a fresh tag (`research#1`, `write#2`, `edit#3`) so the same atom
could appear twice in one flow without colliding. The last step is an `alias`: the flow built
its output under `edit#3`, the runner reads it under `out`, so one extra node copies the
value across. That alias is the only bookkeeping the boundary costs.

## Running a flow

`run(value, *, llm=None, budget=100, policy=None, halt_on_error=True)` compiles the flow,
seeds the input, executes to "the output exists" (capped by `budget` supersteps; the default
100 is a runaway guard for loops that never satisfy their `until`, pass `budget=None` to
lift it), and returns an `Outcome`:

```python
run.value    # the produced output, or None if the run never got there
run.ok       # finished and produced the output
run.reason   # "goal" | "error" | "budget" | "stalled"
run.errors   # error facts from failed nodes, [] when clean
run.steps    # the full StepReport trace
run.view     # the final snapshot
run.unwrap() # the value, or raise RunError if the run did not finish clean
```

`reason` is worth reading on every failure. `"error"` means a node failed and `errors` names
it with its message. `"budget"` means the step cap fired first, the usual suspect being a
loop that never satisfied its `until`. `"stalled"` means the system went quiet without
producing the output, which is almost always a wiring gap. A failing node never surfaces as
a raw traceback out of `run`; it comes back as data on the `Outcome` (the full traceback
rides in the error fact's `meta["traceback"]` when you need it). By default the run stops at
the first failed node; `halt_on_error=False` lets the rest of the system keep going, so the
run can still reach `reason="goal"` with `errors` non-empty, and `ok` stays False either
way.

`stream(value, ...)` is the same call as an async iterator of `StepReport`, for watching the
run unfold live. The `llm` argument is the default backend for every LLM node, covered next.

When you need to own the store, the seed facts, or the terminate condition, drop to the
explicit seam: `.system(entry, out)` compiles the flow to an engine `System`, and you hand it
to a `ReactiveExecutor` yourself (see the [engine page](engine.md)). `run` is that same path
with everything derivable derived.

## Atoms

An atom is a leaf arrow, the smallest `Flow`. Two factories produce one, split by mechanism:
`action` is code, `agent` is a model call. The word agent always means LLM-backed here; the
engine's universal unit is the `Node`, and both atoms compile to nodes. Both return a
`Flow[A, B]` and compose with the same operators.

### action

`action` lifts a python function. The body is the behavior.

```python
# ActionFn[A, B] = Callable[[A], Awaitable[B]] | Callable[[A, View], Awaitable[B]]
def action(fn: ActionFn[A, B], *, name: str | None = None) -> Flow[A, B]: ...
```

The function has the signature `async (input: A) -> B`, or `async (input: A, view: View) -> B`
when it needs the store. The first argument is the value flowing in, already unwrapped from its
fact, typed as `A`. The return value, typed `B`, becomes the arrow's output. `view` is the
read-only snapshot of the whole store, there if a stage needs to look at something beyond its
direct input; the trailing argument is optional and supplied only when you declare it, so a body
that ignores the store just omits it. The types on the
signature are the types of the arrow, so write them honestly rather than reaching for `Any`:
`research` above is a `Flow[str, str]`, and that annotation is what makes the composition
checkable. `name` overrides the function's `__name__` in traces and error tags; pass it when
lifting a lambda.

### agent

`agent` lifts a prompt. The behavior is data, not code, which is what lets an LLM node be
authored without hand-writing a model call.

```python
def agent(
    name, *, prompt, input=None, takes=str, returns=str, labels=None, llm=None,
) -> Flow[A, B]: ...
```

`prompt` is the static system prompt. `takes` and `returns` declare the arrow's types,
defaulting to `str -> str`, so an `agent` composes under `ty` exactly like an `action`. The
node does not bind a backend itself; `llm` (below) is injected per node or as a compile-time
default, which keeps the SDK agnostic about which backend runs.

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

### agent over state

A stateless chain passes one value forward, but a loop, a swarm, or a chat threads a *state*
through every node: each node reads part of it, calls the model, and folds the reply back in.
The reading side is a keyword: `input`, a template for what the model sees, rendered over the
node's input (dict keys or model fields by name, store tags as a fallback, `{input}` for the
whole value; a typo fails the node with the missing key named). The writing side is
composition, not a parameter. Two combinators on the flow thread a dict state past the step,
and they work on any flow, an `action` or a nested system as much as an `agent`:

- `.into("key")` puts the flow's output under that key of the state and passes the rest
  through.
- `.merge()` folds a structured output's fields into the state (`returns` should be a
  model). The output decides which keys change, which is what lets a handoff target ride
  inside the reply.

Both return `Flow[dict, dict]`, the state-preserving shape `.loop` wants; the flow under
them takes the state, so declare `takes=dict`.

```python
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
When behavior genuinely needs code (a computation, a dynamic fan-out), `action` is the escape
hatch; the template and the state combinators exist so state threading alone never forces
you into it.

### agent as a classifier: labels

`labels` constrains an agent's output to one label from a finite set, making it a
`Flow[A, str]` router: the node shape that drives a `branch` when the route is chosen by the
model rather than by data already in the state.

```python
route = agent("route", prompt="Pick the topic:", labels=["math", "prose"], llm=some_llm)
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

The label set rides to the backend as a `Literal` in `returns`, so a structured backend
cannot produce anything outside it, and the reply is validated against `labels` regardless.
The classifier runs first and writes its label, the router sends the original input to the
chosen case, and exactly one case fires. A plain `Callable` selector still works and saves
the extra step; reach for `labels` when the choice itself needs a model. It does not combine
with `returns` (the label set is the return type); to land the label in a dict state, e.g. a
group-chat manager writing who speaks next, compose:
`agent(..., labels=[...], takes=dict).into("speaker")`.

### LLM

`agent` is agnostic about how a prompt turns into a value. That seam is one protocol, and it
is a parameter of the factory, not a way into the engine.

```python
class LLM(Protocol):
    async def complete(
        self, prompt: str, input: Any, view: View, returns: Any = str
    ) -> Any: ...
```

`returns` carries the declared output type of the node, so a backend that supports structured
output can produce that type directly; a plain text backend ignores it. Anything with that
method is a backend: an LLM client, a whole framework, a stub, a fake in a test. The SDK never
imports a provider. This is the LLM-agnostic point made concrete. An `action` is a model-free
atom, an `agent` is the same atom shape with an `LLM` behind it, and the two compose without
distinction.

The binding has two levels. A node can carry its own backend (`llm=` on the factory), and a
whole composition gets a default at the boundary: `.system(entry, out, llm=...)` or
`.run(value, llm=...)`. Per-node bindings win, so a flow can run one node on a different
model and the rest on the default. A node with no backend from either level fails at compile
time, with its name in the message, never mid-run.

## Sequence: `+`

`a + b` runs `a`, then feeds its output to `b`.

```python
def __add__(self, other: Flow[B, C]) -> Flow[A, C]: ...
```

Read the type: a `Flow[A, B]` plus a `Flow[B, C]` is a `Flow[A, C]`. The middle type `B` has
to line up, which is the entire safety claim. If you write `research + edit` where one yields
a draft and the other expects something else, the checker rejects the `+` itself, at the line
where you wrote it, before any run.

## Parallel: gather

`gather(a, b, ...)` runs several arrows on the same input and collects their outputs into a
list. It is the only parallel combinator; there is no binary product operator.

```python
def gather(*flows: Flow[A, B]) -> Flow[A, list[B]]: ...
```

A handful of `Flow[A, B]` become a `Flow[A, list[B]]`. Every branch reads the same `A`, the
runtime runs them together, and the result is the list of their outputs in branch order.
There is no separate join operator. The join is an ordinary next stage that consumes the list.

```python
from collections import Counter

from fedotmas.sdk import action, gather


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

All three solvers run together, `gather#1` collects the list, `majority` reduces it. This is
the shape that voting and mixture-of-agents want, and the `list[B]` output makes the reducer
mandatory by type: a bare `gather` is not yet a usable value, it is a list waiting for a fold.

## Branch

`branch` routes the input to exactly one of several cases, picked at runtime by a label.

```python
def branch(
    select: Callable[[A], str] | Callable[[A, View], str] | str | Flow[A, str],
    cases: dict[str, Flow[A, B]],
) -> Flow[A, B]: ...
```

`select` picks the key: a callable over the input (optionally over the input and the view), a
state key (`branch("station", ...)` routes by `state["station"]`, the declarative form), or a
label-producing agent flow when the choice itself needs a model. Only the case under that key is fed an input fact, so only its
sub-flow runs, and every case converges to the one branch output. A label outside `cases`
fails the route node with the label and the case set in the message. Each case is a full
`Flow[A, B]`, which means a case can itself be a chain, a parallel block, or another branch.

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
def loop(
    self: Flow[A, A],
    until: Callable[[A], bool] | Callable[[A, View], bool] | Condition | str,
    *, budget: int | None = 100,
) -> Flow[A, A]: ...
```

`until` reads the state after each round: a callable (over the state, optionally the state and
the view), a state key (`.loop(until="done")`
stops when `state["done"]` is truthy), or a `Condition`, the declarative comparison
(`Condition(key="rounds_left", op="lte", value=0)`) for conditions a bare key cannot say; the
ordered ops (`gt`/`lt`/`gte`/`lte`) require a `value=` and a present key, the non-comparing
ops (`truthy`/`not`/`exists`) reject a stray one, and both complain by name. The key and
Condition forms are data, which is what a program emitting a system can write. Each round
runs the body in its own inner store as one outer superstep, so the run's budget caps how
many rounds happen, and `.loop`'s own `budget=` caps the supersteps inside one round
(`None` lifts it).

The signature has a sharp edge worth reading. The receiver is typed `self: Flow[A, A]`, an
arrow whose input and output are the same type. You can only call `.loop` on a
state-preserving flow, because a loop has to feed each round's output into the next round, and
that is only coherent when the two types match. Try `.loop` on a `Flow[str, int]` and the
checker refuses: the state contract is enforced by the type, not by a comment.

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

Not every part of a system is a tidy arrow. Some work is opportunistic: a set of rules that
fire whenever the store happens to satisfy them, in no fixed order, converging on a goal. That
is the blackboard surface, written with `rule` and `blackboard`, and it does not have a single
`A -> B` shape to type. `nest` is how such a sub-system enters the arrow world as one node.

```python
def nest(
    target: System | Flow[A, B] | Board, *, entry: str, out: str,
    until: Terminate | None = None, budget: int | None = 100,
) -> Flow[A, B]: ...
```

It wraps a whole sub-system. At runtime the node spins up its own inner store, seeds it with
the incoming value under `entry`, runs the sub-system to its goal (`until`, defaulting to "the
`out` fact exists"), and writes that one result outward. The boundary is typed, the interior
is opaque. The inner run is one superstep of the outer system, so the outer budget cannot
interrupt it; `budget` caps the inner supersteps instead (`None` lifts it). An inner failure
halts the inner run and surfaces as this node's error fact.

```python
from fedotmas.sdk import Flow, Rule, action, blackboard, nest

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

From the outside, `nest#2` is a single step. The three-rule investigation ran to its
conclusion inside its own store and surfaced one fact. That is why `solve` drops into a plain
`frame + solve + report` chain as if it were an atom.

Two things about `nest`. First, it takes a `Board`, a raw `System`, or a `Flow`, so it is also
the primitive for nesting one flow inside another as a self-contained unit, not only for
absorbing a blackboard; a `Flow` or `Board` target picks up the outer flow's default `llm` as
its fallback backend, while a `System` is already compiled and keeps its own bindings.
Second, because the wrapped target has no static arrow type, the
checker cannot infer the boundary types. You annotate them yourself
(`solve: Flow[str, str] = nest(...)`), and that annotation is load-bearing: it is what the
checker uses to verify the stitch on either side. Feed a `str` into a flow built around a
`Flow[list[str], str]` nest and the mismatch is caught.

## Why the types

Everything above leans on one idea. The runtime values are `Any` at execution time; the types
live only at design time, checked by `ty` (or mypy) before you run. They buy correctness by
construction. An unreduced `gather` is a `list` with nowhere to go that the next stage must
consume, a loop over a non-state-preserving body is a receiver
that does not match `Flow[A, A]`. Each of these is a static error at the line you wrote,
rather than a wrong fact discovered mid-run.

The payoff scales past hand-written systems. A typed Python arrow algebra is a small, prunable
search space and a far better target for a program that generates systems than a freeform
diagram. The same property that catches your mistake prunes a generator's.

## The blackboard surface

Not every system is an arrow. When activation is opportunistic, when agents fire in no fixed
order as the store happens to satisfy them, there is no `A -> B` shape to type. For that the SDK
has a second surface: the blackboard.

A rule is a self-activating node: a condition paired with a step. The step is code (`fn`) or,
like the agent atom, a prompt: `prompt` plus an optional `input` template rendered over the
rule's input with store tags as fallback, exactly one of the two. For the common produce-once
shape the condition is derived from `reads` and `writes` (fire when the read fact is present
and the written one is not yet), so a pipeline rule needs no trigger. You write `when` only
when activation is genuinely opportunistic, several rules contending on one fact, or a
condition over more than one read. Its declarative form is a list of fact tags that must all
exist, with a `!` prefix for a fact that must be absent; a callable over the `View` is the
escape hatch for conditions beyond presence. `reads` names the one fact fed to the step as
its input; a rule over several facts conditions on them with `when` and reads them off the
view (or pulls them into an `input` template by tag).

```python
@dataclass
class Rule:
    name: str
    fn: StepFn | None = None                       # code step...
    writes: str = ""
    reads: str = ""
    when: Callable[[View], bool] | Sequence[str] | None = None   # defaults to produce-once
    meta: dict = field(default_factory=dict)       # rides to the agent, e.g. an auction bid
    prompt: str | None = None                      # ...or a prompt step over the LLM seam
    input: str | None = None                       # template for what the model sees
    returns: Any = str                             # the prompt step's output type
    llm: LLM | None = None                         # per-rule backend override


def blackboard(*rules: Rule, llm: LLM | None = None) -> Board: ...
```

`blackboard` assembles rules into a `Board`, and `llm` is the default backend for prompt rules
that did not bind their own (a prompt rule with no backend from either level fails here, by
name). A board runs symmetrically with a flow: `board.run(seed, goal=...)` takes the seed
facts as a tag -> value dict and the tag to read the result back from, and returns the same
`Outcome`; `board.stream` is the same run yielded step by step. An `llm` passed at
`board.run(...)` is the last-resort backend, behind the board default and the per-rule
binding, and `halt_on_error=False` works the same as on `Flow.run`. `board.system` is the
raw engine `System` when you want executor-level control. A
linear investigation is prompts all the way down and writes no triggers:

```python
from fedotmas.sdk import Rule, blackboard

investigation = blackboard(
    Rule("hypothesizer", prompt="Propose one testable hypothesis.", reads="question", writes="hypothesis"),
    Rule("researcher",   prompt="State one supporting piece of evidence.", reads="hypothesis", writes="evidence"),
    Rule("verifier",     prompt="Weigh and conclude in one line.", reads="evidence", writes="conclusion"),
    llm=some_llm,
)

run = await investigation.run({"question": "what is it?"}, goal="conclusion")
```

Because a rule's `input` template falls back to store tags, a rule that weighs several facts
at once stays declarative: `input="Evidence: {evidence}\nObjection: {objection}"` pulls both
straight off the blackboard.

```
step 0: ['hypothesizer'] -> ['hypothesis']
step 1: ['researcher'] -> ['evidence']
step 2: ['verifier'] -> ['conclusion']
conclusion: X confirmed
```

That reads like a chain, because it is one. The surface earns its keep when activation is not
linear. Here `researcher` and `skeptic` both wake on the same hypothesis and run together, and
`verifier` waits on two independent facts at once, a condition no single read expresses, so it
spells out `when`:

```python
blackboard(
    Rule("hypothesizer", hypothesize, writes="hypothesis", reads="question"),
    Rule("researcher",   research,    writes="evidence",   reads="hypothesis"),
    Rule("skeptic",      doubt,       writes="objection",  reads="hypothesis"),
    Rule("verifier",     verify,      writes="conclusion", reads="evidence",
         when=["evidence", "objection", "!conclusion"]),
)
```

```
step 0: ['hypothesizer'] -> ['hypothesis']
step 1: ['researcher', 'skeptic'] -> ['evidence', 'objection']
step 2: ['verifier'] -> ['conclusion']
```

One invariant to know: a rule re-fires per new version of the facts it names. The engine is
edge-triggered, firing a node at most once per distinct set of facts matched by `reads` plus
the positive `when` tags, so a fresh `evidence` re-arms `verifier` above. A rule with a
callable `when` and no `reads` names no facts and fires at most once per run; give it `reads`
if it is meant to wake again.

The order fell out of the facts, not a wiring. Inside a blackboard there are no arrow types and
so no static check; that is the price of an open shape, and the reason to keep blackboards for
work that genuinely has no fixed topology. To use a goal-terminating blackboard as one node in a
flow, wrap it with `nest`.

A rule also carries `meta`, a dict that rides to the node and reads back as
`node.describe().meta`. A `Policy` uses it to choose a winner without a side table, which is how
contract-net puts the bid on the bidder: `AuctionSelect(key=lambda n, v: n.describe().meta["bid"])`.

## When a flow is the wrong shape

A flow is the right tool when the topology is known when you write it: a chain, a fan-out, a
router, a refinement loop. It is the dataflow subset of what the runtime can do, and within
that subset it gives you static checking the raw runtime cannot.

Some systems do not have a fixed topology. The width is decided at runtime, the next speaker is
chosen by a manager, work is handed off dynamically, a task is auctioned to the best bidder.
Those are not arrows. They live on the blackboard surface (authored triggers, optionally a
runtime policy that picks who fires), where there is no shape to derive and so nothing to type.
Forcing them into an arrow would be a category error. When such a system does converge on a goal,
`nest` brings its result back across the boundary as a single typed node. Reach for a flow
where the shape is fixed, reach for the blackboard where order is emergent, and let `nest` be
the seam between them.

## Reference

| Import                       | What it is                                                   |
|------------------------------|--------------------------------------------------------------|
| `sdk.Flow`                   | the typed arrow `Flow[A, B]`, a lazy dataflow fragment        |
| `sdk.action`                 | wrap a typed async function as a mechanical atom              |
| `sdk.agent`                  | lift a prompt into an LLM atom; `input` template, `labels` classifier |
| `sdk.LLM`                    | the LLM seam, one async `complete(prompt, input, view, returns)` |
| `sdk.Condition`              | a declarative predicate over one state key, for `.loop` (data, not code) |
| `Flow.__add__` (`+`)         | sequence, `Flow[A, B] + Flow[B, C] -> Flow[A, C]`             |
| `sdk.gather`                 | parallel, `*Flow[A, B] -> Flow[A, list[B]]`                  |
| `sdk.branch`                 | route to one case by a label: callable, state key, or a labels agent |
| `Flow.loop`                  | iterate a state-preserving flow until a callable, state key, or `Condition` clears; `budget=` caps one round |
| `Flow.into` / `Flow.merge`   | thread a dict state past a step: output under one key / structured output folded in |
| `sdk.nest`                   | run a whole sub-system (`Board`, `System`, or `Flow`) as one typed node; `budget=` caps its inner run |
| `Flow.system`                | compile to a runnable `System`, given `entry`/`out` tags and a default `llm` |
| `Flow.run` / `Flow.stream`   | compile and execute on one input; returns `Outcome` / yields `StepReport` |
| `sdk.Outcome`                | the outcome: `.value`, `.ok`, `.reason`, `.errors`, `.steps`, `.unwrap()` |
| `Outcome.unwrap` / `sdk.RunError` | return the value, or raise `RunError` if the run did not finish clean |
| `sdk.Rule`                   | a self-activating blackboard node, code (`fn`) or prompt (`prompt`/`input`/`returns`), plus `writes`/`reads`, optional `when` (tag sequence, `!` for absent) and `meta` |
| `sdk.blackboard`             | assemble rules into a `Board`: `.run(seed, goal=...)`, `.stream`, `.system`, default `llm` for prompt rules |

Everything above re-exports from `fedotmas.sdk`. Two surfaces (`flow`, `blackboard`) filled by
two atoms (`action` is code, `agent` is a model call). Flat imports are safe, no name shadows
a stdlib import; `from fedotmas import sdk` with the `sdk.` prefix is available if you want
explicit provenance.

Things to keep in mind:

- A flow is lazy. It allocates agents and tags only at `.system(entry, out)` (or `.run`), so
  it is free to reuse and nest. An LLM node with no backend bound, per node or as the
  compile-time default, fails there, not mid-run.
- An atom is a function (`action`) or a prompt over an `LLM` (`agent`; agent always means
  LLM-backed). Both are the same `Flow` and compose alike, and the SDK never imports an LLM
  provider.
- State threading is declarative: `input` templates pick what the model sees, `.into`/`.merge`
  fold the output back into a dict state, branch routes by a state key, loop stops on one.
  Reach for `action` only when behavior is genuinely code.
- Failure is data. `Outcome.reason` distinguishes goal, error, budget, and stalled; `errors`
  names the failed node and its message, with the traceback in the fact's `meta`.
- The types are a design-time contract. They are checked before the run and are `Any` at
  runtime, which is why the function signatures should be honest.
- `+` and `.loop` enforce their stitch crisply. `branch` is looser, keep its cases homogeneous.
- The join is never a special operator. A `gather` list is consumed by an ordinary next stage,
  and the type makes that consumption mandatory.
- Use a flow where the topology is fixed. Use the blackboard where order is emergent, and `nest`
  to carry an emergent sub-system back into the arrow world.
