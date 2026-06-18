# Examples

## engine/

Every file runs the **same** `ReactiveExecutor` over the **same** `Store` + `Node`
contract. Nothing in the engine changes between patterns, only the nodes, their triggers,
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

## sdk/

The typed SDK surface over the same engine: build atoms with `action`/`agent`, compose them
with the arrow operators, and run with `flow.run(value)` / `flow.stream(value)` (which return
an `Outcome` / yield `StepReport`s — no executor wiring by hand). These run with no API key
(`agent` nodes use a small `FakeLLM` stub). See [`docs/flow.md`](../docs/flow.md).

| File | SDK surface shown |
|---|---|
| `sdk/composition.py` | `+` sequence and `gather(...) + reducer` fan-out, run via `.stream`/`.run` |
| `sdk/gather.py` | `gather(a, b, c) + majority` — self-consistency voting |
| `sdk/branch.py` | `branch(classify, cases)` — route by a plain selector function |
| `sdk/factories.py` | `action` + `agent` atoms (`FakeLLM`); a `labels=` classifier driving a `branch` |
| `sdk/loop.py` | `.loop(until=...)` — reflection and evaluator-optimizer over a dict state |
| `sdk/state.py` | dict state: `.into` / `.merge`, branch by state key, loop until a key |
| `sdk/blackboard.py` | the blackboard surface: `Rule` + `blackboard`, produce-once and `when` triggers, goal stop |
| `sdk/nest.py` | `nest(board, ...)` — a goal-terminating blackboard as one typed flow node |

## sdk-llm/

The same SDK against real models. Each file wires a backend through the `LLM` seam and reads
an API key, so they need a `.env` (e.g. `OPENAI_API_KEY=...`) and run via `uv run python
examples/sdk-llm/<file>.py`.

| File | Pattern shown |
|---|---|
| `sdk-llm/backends.py` | the swappable `LLM` seam: a hand-written LangChain backend beside `PydanticAI`; `gather + assemble` |
| `sdk-llm/dag.py` | diamond DAG: `extract + gather(support, oppose) + balance` |
| `sdk-llm/orchestrator.py` | orchestrator-workers: `planner -> dynamic fan-out (action) -> synthesize` |
| `sdk-llm/swarm.py` | handoff/swarm: `.merge()` handoffs, branch by `station`, loop until `done` |
| `sdk-llm/blackboard.py` | prompt rules on the blackboard, a `when`-gated verifier, goal stop |
