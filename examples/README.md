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

The embedded Python surface (`fedotmas.sdk`). Typed `Flow[A, B]` arrows compose with `+`
(sequence), `*` / `gather_all` (parallel), `branch`, `.loop`, and `nest`, the type parameters
making each stitch checkable by `ty`. The rule surface (`blackboard`) sits beside them for
emergent activation. Every file compiles to the same engine `System` and streams its trace.

| Shape | File | Surface |
|---|---|---|
| atom factories | `sdk/factories.py` | `action` (code) and `agent` (LLM, incl. `labels` classifier) lift leaves into `Flow` |
| stateful atoms + run | `sdk/state.py` | `input=` templates, `into`/`merge`, `branch("key")`, `.loop("key")`, `Flow.run` |
| seq, parallel-into-seq | `sdk/composition.py` | `a + b + c`, `(a * b) + c` |
| loop (reflection, eval-optimizer) | `sdk/loop.py` | `body.loop(until)` |
| branch / router | `sdk/branch.py` | `branch(select, cases)` |
| n-ary parallel + reduce | `sdk/gather_all.py` | `gather_all(a, b, c) + reduce` |
| blackboard as a node | `sdk/nest.py` | `frame + nest(bb) + report` |
| rule surface | `sdk/blackboard.py` | `blackboard(*rules)` |

## sdk-llm/

The SDK on real models via the optional `[llm]` extra. The `LLM` contract is the seam: any
provider or framework wraps into it, and `adapters.pydantic_ai.PydanticAI` is the default
backend, bound once at `.run()` / `blackboard()` rather than on every node. Four examples,
chosen to be orthogonal: each exercises a different surface of the SDK, and together they
cover all of it. Needs an OpenAI key in `.env`; run with the examples group, e.g.
`uv run --group examples python examples/sdk-llm/dag.py`.

| Shape | File | SDK surface |
|---|---|---|
| DAG with a parallel block | `sdk-llm/dag.py` | stateless arrows: `extract + (support * oppose) + balance`, `Flow.run` and `FlowRun` |
| Blackboard | `sdk-llm/blackboard.py` | declarative prompt rules (`rule(prompt=...)`), opportunistic `when`, `input` template over store tags, `board.run` |
| Master orchestrator | `sdk-llm/orchestrator.py` | structured plan sized at runtime, `action` as the code escape hatch for dynamic fan-out |
| Handoff / Swarm | `sdk-llm/swarm.py` | stateful atoms end to end: `input=` templates, `merge=` structured handoff, `branch("station")` inside `.loop(until="done")` |
