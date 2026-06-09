# Examples

Organized by layer, lowest to highest.

- `engine/` raw engine. Patterns built directly on the `Agent` contract with hand-written
  triggers. These are the universality proof and double as reference implementations.
- `combinators/` the edge surface, built with `dsl.combinators`. Steps are plain async
  functions, the combinator derives tags, triggers, and wiring from the fixed shape.
- `presets/` the rule surface (`dsl.rules`) and, later, named pattern constructors built
  on top. A rule pairs an author-written condition with a step; there is no shape to
  derive a trigger from, so the author writes it. This is the blackboard superset the
  combinators cannot express.

Run any one: `uv run python examples/<dir>/<name>.py` (each streams its superstep trace).

## engine/

Every file runs the **same** `ReactiveExecutor` over the **same** `Store` + `Agent`
contract. Nothing in the engine changes between patterns, only the agents, their triggers,
the `Policy`, and the `Terminate` condition differ. That is the universality claim, checked
on running code.

| Pattern | File | Engine mechanism exercised |
|---|---|---|
| Prompt Chaining (P1) | `engine/prompt_chaining.py` | seq via fact dependency, edge-trigger dedup |
| Sectioning (P2) | `engine/sectioning.py` | fan-out + join (count-gated trigger) |
| Self-Consistency (P3) | `engine/voting.py` | replicas keyed by identity + majority aggregator |
| Ensemble Voting (P4) | `engine/voting.py` | same shape as P3, distinct agents |
| DAG (P5) | `engine/dag.py` | diamond dependency, join on two upstreams |
| Evaluator-Optimizer (P6) | `engine/eval_optimizer.py` | loop until goal, generator/critic alternation |
| Mixture-of-Agents (P7) | `engine/mixture_of_agents.py` | layered parallel with aggregation between layers |
| Router (P8) | `engine/router.py` | label fact activates exactly one target |
| Orchestrator-Workers (P9) | `engine/orchestrator_workers.py` | runtime-decided width, batch-mapped worker |
| Handoff / Swarm (P10) | `engine/swarm.py` | active-fact handoff, loop until done |
| Group Chat (P11) | `engine/group_chat.py` | manager/speaker turns over a shared transcript |
| Hierarchical Teams (P12) | `engine/hierarchical.py` | a sub-System wrapped as one agent (nesting) |
| Blackboard (P13) | `engine/blackboard.py` | author-written triggers, self-activation, goal stop |
| Contract-Net (P14) | `engine/contract_net.py` | `AuctionSelect` Policy picks the winning bidder |
| Reflection (P15) | `engine/reflection.py` | single agent self-revises (critic folded in) |
| Debate (P16) | `engine/debate.py` | parallel rounds judged in a loop, transcript accrues |

## combinators/

| Combinator | File | Equivalent engine example |
|---|---|---|
| `seq` | `combinators/seq.py` | `engine/prompt_chaining.py` |
| `parallel` / `join` | `combinators/parallel.py` | `engine/sectioning.py` |
| `branch` | `combinators/branch.py` | `engine/router.py` |
| `loop` | `combinators/loop.py` | `engine/eval_optimizer.py`, `engine/reflection.py` |

## presets/

| Surface | File | Equivalent engine example |
|---|---|---|
| `rules` / `blackboard` | `presets/blackboard.py` | `engine/blackboard.py` |
