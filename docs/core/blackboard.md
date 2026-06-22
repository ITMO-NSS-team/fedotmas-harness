# Blackboard surface

The blackboard is the SDK's second surface, for work with no fixed topology.
Rules self-activate when the store satisfies them, in no order anyone wired.
See [Concepts](concepts.md) for when to reach for it over a [flow](flow.md), and [`nest`](flow.md#nest) for folding a goal-terminating board into one typed flow node.

Not every system is an arrow.
When activation is opportunistic, when nodes fire in no fixed order as the store happens to satisfy them, there is no `A -> B` shape to type.
For that the SDK has a second surface: the blackboard.

A rule is a self-activating node: a condition paired with a step.
The step is code, a `Rule` carrying an `fn` (`async (input)` or `async (input, view)`), the reactive counterpart of the flow surface's `action`.
For the common produce-once shape the condition is derived from `reads` and `writes` (fire when the read fact is present and the written one is not yet), so a pipeline rule needs no trigger.
You write `when` only when activation is genuinely opportunistic, several rules contending on one fact, or a condition over more than one read.
Its declarative form is a list of fact tags that must all exist, with a `!` prefix for a fact that must be absent; a callable over the `View` is the escape hatch for conditions beyond presence.
`reads` names the one fact fed to the step as its input; a rule over several facts conditions on them with `when` and reads them off the view.

```python
@dataclass
class Rule:
    name: str
    fn: StepFn | None = None                       # code step: async (input) or (input, view)
    writes: str = ""
    reads: str = ""
    when: Callable[[View], bool] | Sequence[str] | None = None   # defaults to produce-once
    meta: dict = field(default_factory=dict)       # rides to the node, e.g. an auction bid


def blackboard(*rules: Rule) -> Board: ...
```

`blackboard` assembles rules into a `Board`.
A board runs symmetrically with a flow: `board.run(seed, goal=...)` takes the seed facts as a tag -> value dict and the tag to read the result back from, and returns an `Outcome`; `board.stream` is the same run yielded step by step, and `halt_on_error=False` works the same as on `Flow.run`.
`board.system` is the raw engine `System` when you want executor-level control.
A linear investigation is a chain of code rules that writes no triggers:

```python
from fedotmas import Rule, blackboard

investigation = blackboard(
    Rule("hypothesizer", hypothesize, reads="question",  writes="hypothesis"),
    Rule("researcher",   research,    reads="hypothesis", writes="evidence"),
    Rule("verifier",     verify,      reads="evidence",   writes="conclusion"),
)

run = await investigation.run({"question": "what is it?"}, goal="conclusion")
```

Because a code rule can read the `view`, a rule that weighs several facts at once stays simple: it conditions on them with `when` and pulls each off the view inside its `fn`.

```
step 0: ['hypothesizer'] -> ['hypothesis']
step 1: ['researcher'] -> ['evidence']
step 2: ['verifier'] -> ['conclusion']
conclusion: X confirmed
```

That reads like a chain, because it is one.
The surface earns its keep when activation is not linear.
Here `researcher` and `skeptic` both wake on the same hypothesis and run together, and `verifier` waits on two independent facts at once, a condition no single read expresses, so it spells out `when`:

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

One invariant to know: a rule re-fires per new version of the facts it names.
The engine is edge-triggered, firing a node at most once per distinct set of facts matched by `reads` plus the positive `when` tags, so a fresh `evidence` re-arms `verifier` above.
A rule with a callable `when` and no `reads` names no facts and fires at most once per run; give it `reads` if it is meant to wake again.

The order fell out of the facts, not a wiring.
Inside a blackboard there are no arrow types and so no static check; that is the price of an open shape, and the reason to keep blackboards for work that genuinely has no fixed topology.
To use a goal-terminating blackboard as one node in a flow, wrap it with `nest`.

A rule also carries `meta`, a dict that rides to the node and reads back as `node.describe().meta`.
A `Policy` uses it to choose a winner without a side table, which is how contract-net puts the bid on the bidder: `AuctionSelect(key=lambda n, v: n.describe().meta["bid"])`.

## Reference

| Import | What it is |
|--------|------------|
| `Rule` | a self-activating code node: `fn`, plus `writes`/`reads`, optional `when` (tag sequence, `!` for absent) and `meta` |
| `blackboard` | assemble rules into a `Board`: `.run(seed, goal=...)`, `.stream`, `.system` |
| `Board` | the assembled blackboard; `.run` is symmetric with `Flow.run` and returns an `Outcome` |

Things to keep in mind:

- A rule's condition defaults to produce-once (fire when `reads` is present and `writes` is not).
  Write `when` only when activation is genuinely opportunistic.
- `when` is data: a sequence of tags that must all exist, `!tag` for one that must be absent.
  A callable over the `View` is the escape hatch.
- A rule re-fires per new version of the facts it names (`reads` plus the positive `when` tags).
  A callable `when` with no `reads` fires at most once per run.
- There are no arrow types inside a blackboard, so no static check.
  Keep it for work that genuinely has no fixed topology.
- `meta` rides to the node and reads back as `node.describe().meta`, which is how a `Policy` picks a winner (e.g. contract-net auctions).
