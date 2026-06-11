# Engine

The engine is the part of fedotmas that actually runs a multi-agent system. It has no
notion of graphs, prompts, or LLMs. It knows three things: a shared store of facts, a set
of **nodes** that read and write those facts, and a loop that decides who runs next.

A note on the word: this page says "agent" for the things acting on the store, because that
is what they are in a multi-agent system. But the contract they implement is called `Node`,
deliberately. The engine does not care whether a node wraps an LLM agent, a plain function,
or a whole team; the SDK reserves the word agent for its LLM-backed atom specifically.

Everything else in the framework (the DSL, the pattern presets) is a way to produce input
for this engine. If you understand the engine, you understand the runtime.

## The mental model

There is one shared place where state lives, called the **Store**. State is a growing list
of **facts**. A fact is a tagged value, like `draft:1 = {...}` or `topic = "witcher"`.

Agents do not call each other. Each agent watches the store and declares "I am ready when
the store looks like this". The engine runs in rounds. In each round it takes a single
snapshot of the store, asks every agent whether it is ready, runs the ready ones at the
same time, and then writes all of their new facts back into the store. Then it takes a new
snapshot and repeats.

That round is called a **superstep** (the model is BSP, bulk-synchronous parallel). The
key consequence: agents that run together in one superstep all see the same snapshot, and
none of them sees what the others wrote until the next superstep. State only moves forward
at the boundary between supersteps.

This is the whole engine. The rest of this page is the pieces that make it concrete.

## A first run

Three agents in a chain. The researcher waits for a `topic`, the writer waits for
`research`, the editor waits for a `draft`. Nobody wires them together. Each just declares
what it reads, and the data dependency creates the order.

```python
import asyncio

from fedotmas.engine import as_node
from fedotmas.engine import Fact, Goal, ReactiveExecutor, Result, Store, System, View


async def research(input: object, view: View) -> Result:
    return Result(writes=[Fact(tag="research", value="raw facts")])


async def write(input: object, view: View) -> Result:
    return Result(writes=[Fact(tag="draft", value=f"draft from {view.value('research')}")])


async def edit(input: object, view: View) -> Result:
    return Result(writes=[Fact(tag="final", value=f"edited {view.value('draft')}")])


async def main() -> None:
    system = System(nodes=[
        as_node(research, name="researcher", reads="topic"),
        as_node(write, name="writer", reads="research"),
        as_node(edit, name="editor", reads="draft"),
    ])
    store = Store()
    async for report in ReactiveExecutor().stream(
        system, store,
        seed=[Fact(tag="topic", value="witcher")],
        terminate=Goal(lambda v: v.exists("final")),
    ):
        print(f"step {report.step}: {report.fired} -> {[f.tag for f in report.writes]}")
    print("final:", store.snapshot().value("final"))
```

Output:

```
step 0: ['researcher'] -> ['research']
step 1: ['writer'] -> ['draft']
step 2: ['editor'] -> ['final']
final: edited draft from raw facts
```

One agent fires per step here because each one's input only appears after the previous one
writes. Nothing scheduled that order. It fell out of what each agent reads.

## Fact

A fact is the unit of state. It is an immutable pydantic model.

```python
class Fact(BaseModel):
    tag: str
    value: Any = None
    producer: str = ""
    step: int = -1
    meta: dict[str, Any] = Field(default_factory=dict)
```

You set `tag` and `value`. The engine fills in `producer` (which agent wrote it) and `step`
(which superstep) when the fact is committed; anything you set explicitly is kept. Seed
facts land just before the store clock, `step=-1` on a fresh store, so a seed and a step-0
write under the same tag stay distinct facts.

Facts are never edited or deleted. To change something, you write a new fact. Tags are
usually versioned for this reason: `draft:1`, then `draft:2`, and so on. The identity of a
fact is `(tag, step, producer)`, exposed as `fact.key`, and the engine uses that key to
track what an agent has already consumed (see
[Triggers](#triggers-and-the-fire-once-rule)). Producer is part of the identity so two
agents writing the same tag in the same superstep count as two distinct facts, not one.

## Store and View

The `Store` holds the facts. You almost never read from it directly. Instead the engine
hands each agent a read-only `View`, which is a snapshot of the store frozen at the start of
the current superstep. The store also owns the logical clock: `store.next_step()` is one
past the highest step ever committed, monotonic across runs over the same store, so fact
keys from a second run never collide with the first.

```python
class View(Protocol):
    def get(self, tag: str) -> Fact | None: ...   # latest matching fact
    def value(self, tag: str) -> Any: ...          # latest value, or None
    def query(self, pattern: str) -> list[Fact]: ...
    def exists(self, pattern: str) -> bool: ...
    def count(self, pattern: str) -> int: ...
```

Patterns are deliberately simple. A pattern is either an exact tag (`"draft:1"`) or a prefix
glob ending in `*` (`"draft:*"`). There are no regexes.

```python
view.value("research")     # "raw facts"
view.query("draft:*")      # [Fact(draft:1, ...), Fact(draft:2, ...)]
view.count("vote:*")       # 5
view.exists("verdict:*")   # True
```

`get` and `value` return the *latest* matching fact and accept the same patterns, so
`view.value("draft:3")` gives the value written under that tag and `view.value("draft:*")`
the newest draft. `query` returns matches in the order they were committed.

!!! note "Why a snapshot, not the live store"
    Every agent in a superstep reads the same frozen view. If two agents run together,
    neither sees the other's writes until the next step. This is what makes parallel runs
    deterministic and free of read-write races. It also means that if you run several copies
    of one agent in parallel, they cannot count each other. Give each copy its own identity
    rather than deriving one from `view.count(...)` at runtime.

## Node

A node is anything that satisfies this contract. It is a `Protocol`, so there is no base
class to inherit and no registration step.

```python
class Node(Protocol):
    name: str
    reads: str

    def trigger(self, view: View) -> bool: ...
    async def invoke(self, input: Any, view: View) -> Result: ...
    def describe(self) -> Card: ...
```

- `name` identifies the node and stamps every fact it writes.
- `reads` is the pattern of facts this node consumes, or several patterns separated by
  whitespace. The engine queries it to decide what to pass as `input` (the matched facts, a
  `list[Fact]`) and to track what the node has already seen: the matched facts are the
  node's re-fire identity (see [Triggers](#triggers-and-the-fire-once-rule)).
- `trigger(view)` returns `True` when the node wants to run, given the current snapshot.
- `invoke(input, view)` does the work and returns a `Result`. It is `async`, so a node is
  free to call an LLM, hit the network, or just compute.
- `describe()` returns a `Card` with metadata. Not used by the loop itself.

To the engine a node is a black box. It can wrap a single function, an LLM call, an entire
external framework, or even another fedotmas system (see
[Nesting](#nesting-a-system-is-an-agent)).

### as_node

You rarely write the protocol by hand. `as_node` wraps an async function into a node.

```python
def as_node(fn, *, name, reads="", trigger=None) -> Node: ...
```

`fn` has the signature `async (input, view) -> Result`. If you do not pass a `trigger`, the
default is "fire when every `reads` pattern has a match"; with empty `reads` it is "never",
so a node without reads needs an explicit trigger to fire at all:

```python
# these are the same agent
as_node(write, name="writer", reads="research")
as_node(write, name="writer", reads="research",
         trigger=lambda v: v.exists("research"))
```

That default is enough for plain chains and fan-outs. For loops, joins, and anything
conditional you pass an explicit `trigger`, covered below.

## Result

`invoke` returns a `Result`. The field the engine acts on is `writes`.

```python
class Result(BaseModel):
    status: Status = Status.OK
    error: str | None = None
    writes: list[Fact] = Field(default_factory=list)
```

`writes` is the single channel through which an agent changes the world. There is no other
way to affect state or to influence what runs next. Want to hand control to another agent?
Write a fact that its trigger is watching for. Want to stop? Write the fact your terminate
condition checks. Routing, handoff, spawning subtasks: all of it is "write a fact that some
trigger reads".

`status` and `error` are how an agent reports failure without raising: return
`Status.ERROR` and the engine treats it exactly like a raised exception (see
[Errors](#errors)).

## System

A `System` is just the bag of nodes you want to run together.

```python
@dataclass
class System:
    nodes: list[Node]
```

There are no edges in it. The wiring lives inside each agent's `reads` and `trigger`. Two
agents interact whenever one writes a fact the other reads. This is why the same `System`
shape can express a pipeline, a fan-out, a loop, or a blackboard. The topology is implied by
the facts, not declared on the side.

## ReactiveExecutor

The executor runs a `System` against a `Store`. There is one implementation,
`ReactiveExecutor`, and it offers two entry points.

`stream` is the primary one. It is an async generator that yields a `StepReport` after every
superstep, so you can watch the run unfold live:

```python
async for report in ReactiveExecutor().stream(system, store, seed=..., terminate=...):
    print(report.step, report.fired)
```

`run` drains the stream and returns a single `Run` with the full trace and the final view:

```python
result = await ReactiveExecutor().run(system, store, seed=..., terminate=...)
print(result.status, len(result.steps))
print(result.view.value("final"))
```

Both take the same keyword arguments:

| Argument    | Meaning                                                          | Default          |
|-------------|------------------------------------------------------------------|------------------|
| `seed`      | Facts committed before the first superstep, as the initial input | `()`             |
| `terminate` | When to stop (see [Terminate](#terminate))                       | run to quiescence|
| `policy`    | How to resolve which ready agents actually fire                  | `FireAll`        |

The reporting types:

```python
@dataclass
class StepReport:
    step: int            # the store clock stamped on this step's writes
    index: int           # 0-based position in this run's trace
    fired: list[str]     # names of agents that ran this step
    writes: list[Fact]   # facts they produced
    errors: list[Fact]   # error facts from agents that failed this step

@dataclass
class Run:
    status: Status       # ERROR if any step recorded errors
    steps: list[StepReport]
    view: View           # final snapshot
    reason: Literal["terminate", "quiescence", "error"]
```

`step` and `index` coincide on a fresh store. They diverge when a run starts over a store
with history: `step` keeps counting from the store clock, `index` from zero. `Budget` counts
`index`, the run's own effort.

`reason` says how the run ended: the terminate condition fired, the system went quiet on
its own, or an agent failed. The three are different situations for whoever inspects the
run, a stalled system in particular (quiescence without the goal fact) usually means a
wiring gap, not success.

### What one superstep does

Each iteration of the loop:

1. Take a snapshot of the store.
2. For each agent, call `trigger(view)`. If it returns `True`, query its `reads` to get the
   input facts.
3. Skip any agent that has already fired on this exact set of input facts (the fire-once
   rule, below).
4. Hand the survivors to the `policy` to pick who actually runs.
5. `await` all chosen agents at once with `asyncio.gather`.
6. Stamp their writes with the agent name and step, commit them in one batch together with
   error facts for any agent that failed, yield a `StepReport`.
7. If any agent failed, stop (default; `halt_on_error=False` keeps going). Otherwise check
   `terminate`. If done, stop. Otherwise repeat.

If no agent is ready, the system has gone quiet. The executor yields one final empty
`StepReport` and stops on its own, even without a terminate condition.

## Errors

A failing agent does not crash the run with a traceback; it becomes data. When `invoke`
raises (or returns `Status.ERROR`), the engine commits a fact tagged `error:{agent name}`
whose value is the message, records it in `StepReport.errors`, finishes the step for the
agents that ran alongside, and stops. The `Run` comes back with `status=ERROR` and
`reason="error"`. The message keeps only `str(exc)`; the full traceback rides in the error
fact's `meta["traceback"]` for debugging. Stopping is the default, not a law:
`ReactiveExecutor(halt_on_error=False)` records the error fact the same way but lets the rest
of the system keep running, and the `Run` still ends with `status=ERROR`.

```python
run = await ReactiveExecutor().run(system, store, seed=...)
if run.status is Status.ERROR:
    for fact in run.steps[-1].errors:
        print(fact.producer, "failed:", fact.value)
```

Because the error is a fact in the store, it is queryable like anything else
(`view.query("error:*")`), and a program inspecting a finished run can see exactly which
node failed on which step and why. Errors from a nested system (a sub-run inside an agent)
surface the same way: the wrapping agent raises, and the outer engine records it as that
node's error fact.

## Triggers and the fire-once rule

This is the one piece of the engine that surprises people, so it is worth a moment.

A trigger is **level-based**: it returns `True` whenever the store currently satisfies a
condition. A naive loop would re-run an agent every superstep for as long as its condition
held. The generator in a refinement loop would fire forever.

The engine prevents this with a fire-once rule. For each agent it remembers the set of fact
keys (`fact.key`) the agent last fired on, and the agent fires only when the facts matched
by its `reads` differ from that set. The store is append-only, so a matched set only ever
grows, and remembering the last one is enough to fire exactly once per distinct input.

This is why versioned tags matter. When the critic reads `draft:1` and writes `verdict:1`,
the generator's input is now a new fact set, so it is allowed to fire again and produce
`draft:2`. Each turn of the loop consumes genuinely new facts, so each turn is a distinct
firing. The loop advances instead of spinning or stalling.

The flip side: the memo key is built from `reads`, not from the trigger. A node with empty
`reads` has the empty fact set as its identity and fires at most once per run, no matter how
long its trigger stays true. A node meant to re-fire on new facts must name them in `reads`
(several patterns are fine, whitespace-separated).

In practice: use the default `exists` trigger for one-shot agents, and write an explicit
trigger for loops and joins. Here is a join, where the aggregator should wait for all three
upstream facts before running:

```python
as_node(join, name="aggregator", reads="out:*",
         trigger=lambda v: v.count("out:*") == 3)
```

## Policy

When more than one agent is ready in the same superstep, the `Policy` decides which of them
actually fire. The default lets them all run.

```python
class Policy(Protocol):
    def select(self, ready: list[Agent], view: View) -> list[Agent]: ...
```

Two are provided. `FireAll` returns everyone (full parallelism, the default). `AuctionSelect`
runs a scoring function over the ready set and fires only the single highest bidder, which is
how a contract-net auction picks a winner:

```python
from fedotmas.engine import AuctionSelect

BIDS = {"w1": 0.3, "w2": 0.9, "w3": 0.5}

ReactiveExecutor().stream(
    system, store,
    seed=[Fact(tag="task", value="haul cargo")],
    policy=AuctionSelect(key=lambda agent, view: BIDS[agent.name]),
)
# only w2 ever fires
```

## Terminate

A terminate condition decides when the run stops. The engine checks it after each committed
superstep. If you pass none, the run continues until the system goes quiet on its own.

```python
class Terminate(Protocol):
    def done(self, view: View, report: StepReport) -> bool: ...
```

Three are built in:

```python
from fedotmas.engine import Budget, Goal, Quiescence

Goal(lambda v: v.exists("final"))   # stop when a predicate over the store holds
Budget(max_steps=8)                 # stop after N supersteps
Quiescence()                        # stop when a step fired nobody
```

They compose with `&` and `|`, which is the usual way to combine a success condition with a
safety cap:

```python
terminate = Goal(approved) | Budget(max_steps=8)
```

The operators live on the built-in conditions; for a `Terminate` you implemented yourself,
`engine.all_of` / `engine.any_of` compose anything matching the protocol.

That reads as "stop when the work is approved, or after 8 steps regardless". The cap matters
for loops where the goal might never be reached.

## A loop: Evaluator-Optimizer

The chain above never reused an agent. This example does. A generator produces a draft, a
critic judges it, and the generator runs again if the critic was not satisfied. It is the
same engine, the only new ingredients are explicit triggers and a composed terminate.

```python
import asyncio

from fedotmas.engine import as_node
from fedotmas.engine import Budget, Fact, Goal, ReactiveExecutor, Result, Store, System, View

THRESHOLD = 3


async def generate(input: object, view: View) -> Result:
    n = view.count("draft:*") + 1
    return Result(writes=[Fact(tag=f"draft:{n}", value={"quality": n})])


def generate_trigger(view: View) -> bool:
    verdicts = view.query("verdict:*")
    return not verdicts or not verdicts[-1].value["approved"]


async def critique(input: object, view: View) -> Result:
    n = view.count("draft:*")
    approved = view.value(f"draft:{n}")["quality"] >= THRESHOLD
    return Result(writes=[Fact(tag=f"verdict:{n}", value={"approved": approved})])


def critique_trigger(view: View) -> bool:
    return view.count("draft:*") > view.count("verdict:*")


def approved(view: View) -> bool:
    verdicts = view.query("verdict:*")
    return bool(verdicts) and verdicts[-1].value["approved"]


async def main() -> None:
    system = System(nodes=[
        as_node(generate, name="generator", reads="verdict:*", trigger=generate_trigger),
        as_node(critique, name="critic", reads="draft:*", trigger=critique_trigger),
    ])
    store = Store()
    async for report in ReactiveExecutor().stream(
        system, store,
        seed=[Fact(tag="task", value="write a haiku")],
        terminate=Goal(approved) | Budget(max_steps=8),
    ):
        print(f"step {report.step}: {report.fired} -> {[f.tag for f in report.writes]}")
```

Output:

```
step 0: ['generator'] -> ['draft:1']
step 1: ['critic'] -> ['verdict:1']
step 2: ['generator'] -> ['draft:2']
step 3: ['critic'] -> ['verdict:2']
step 4: ['generator'] -> ['draft:3']
step 5: ['critic'] -> ['verdict:3']
```

The generator stops firing once `verdict:3` is approved, because its trigger looks at the
last verdict. The fire-once rule keeps each agent advancing through fresh `draft:N` /
`verdict:N` pairs rather than re-running on stale input.

## Nesting: a system is an agent

Because an agent is just the contract, a whole subsystem can be one. Build an inner `System`
with its own `Store`, then wrap it in a class that satisfies the `Agent` protocol and runs
that system inside its `invoke`:

```python
class Team:
    def __init__(self, name, system, *, reads, out):
        self.name, self.reads = name, reads
        self._system, self._out = system, out

    def trigger(self, view):
        return view.exists(self.reads) and not view.exists(self._out)

    async def invoke(self, input, view):
        inner = Store()
        run = await ReactiveExecutor().run(
            self._system, inner,
            seed=[Fact(tag="task", value=view.value(self.reads))],
            terminate=Goal(lambda v: v.exists("summary")),
        )
        return Result(writes=[Fact(tag=self._out, value=run.view.value("summary"))])

    def describe(self):
        return Card(name=self.name)
```

From the outer system's point of view, `Team` is one agent that reads a brief and writes a
result. The nesting is free because there is nothing special to support. The same contract
works at every level.

## Reference

Everything below re-exports flat from `fedotmas.engine`, e.g.
`from fedotmas.engine import Fact, System, ReactiveExecutor, Goal`.

| Import                                  | What it is                                  |
|-----------------------------------------|---------------------------------------------|
| `engine.Fact`                           | tagged immutable value, the unit of state   |
| `engine.Result`                         | what `invoke` returns, `writes` is the channel |
| `engine.View` / `Node`                  | the read snapshot and the node protocol     |
| `engine.Store`                          | the shared blackboard                       |
| `engine.System`                         | the set of nodes to run                     |
| `engine.ReactiveExecutor`               | the superstep loop, `stream` and `run`      |
| `engine.Run` / `StepReport`             | the trace: status, reason, fired, writes, errors |
| `engine.FireAll` / `AuctionSelect`      | resolve who fires in a step                 |
| `engine.Goal` / `Budget` / `Quiescence` | when to stop, composable with `&` `|`       |
| `engine.as_node`                      | wrap an async function as a node            |

Things to keep in mind:

- State only changes through `Result.writes`. There is no other side channel.
- A failing agent ends the run as data: an `error:{name}` fact, `StepReport.errors`,
  `Run.status=ERROR`, `Run.reason="error"`. Check `Run.reason` to tell a finished run from
  a stalled or failed one.
- Facts are append-only and versioned. Never mutate, write a new tag.
- A superstep is the unit of progress. Agents in one step share a snapshot and cannot see
  each other's writes until the next step.
- Triggers are level-based, but the fire-once rule makes an agent run only once per distinct
  input fact set.
- The store owns the step clock, so re-running over the same store gets fresh fact keys. A
  fresh executor carries no fire-once memory, though: it re-fires every ready node over the
  current state and recomputes.
- Give parallel copies of an agent their own identity. They cannot count each other within a
  step.
