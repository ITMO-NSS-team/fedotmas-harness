# Examples

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

## sdk/

The embedded Python surface (`fedotmas.sdk`). Typed `Flow[A, B]` arrows compose with `+`
(sequence), `*` / `gather_all` (parallel), `branch`, `.loop`, and `embed`, the type parameters
making each stitch checkable by `ty`. The rule surface (`blackboard`) sits beside them for
emergent activation. Every file compiles to the same engine `System` and streams its trace.

| Shape | File | Surface |
|---|---|---|
| atom factories | `sdk/factories.py` | `action`, `agent`, `decision` lift leaves into `Flow` |
| seq, parallel-into-seq | `sdk/composition.py` | `a + b + c`, `(a * b) + c` |
| loop (reflection, eval-optimizer) | `sdk/loop.py` | `body.loop(until)` |
| branch / router | `sdk/branch.py` | `branch(select, cases)` |
| n-ary parallel + reduce | `sdk/gather_all.py` | `gather_all(a, b, c) + reduce` |
| blackboard as a node | `sdk/embed.py` | `frame + embed(bb) + report` |
| rule surface | `sdk/blackboard.py` | `blackboard(*rules)` |

## sdk-llm/

The SDK on real models via the optional `[llm]` extra. The `LLM` contract is the seam: any
provider or framework wraps into it, and `adapters.pydantic_ai.PydanticAI` is the default
backend. Every engine pattern is rebuilt here on the high-level surface (`agent`, `decision`,
`action` lifted into `Flow` and composed with `+ * gather_all branch .loop embed`, plus the
`Rule`/`blackboard` surface), so the same 16 patterns read as a few typed arrows rather than
hand-wired triggers. Needs an OpenAI key in `.env`; run with the examples group, e.g.
`uv run --group examples python examples/sdk-llm/prompt_chaining.py`.

| Pattern | File | SDK surface |
|---|---|---|
| Prompt Chaining (P1) | `sdk-llm/prompt_chaining.py` | `agent + agent + agent` |
| Sectioning (P2) | `sdk-llm/sectioning.py` | `gather_all(facets...) + synthesize` |
| Self-Consistency / Ensemble (P3/P4) | `sdk-llm/voting.py` | `gather_all(decision...) + majority` |
| DAG (P5) | `sdk-llm/dag.py` | `extract + (support * oppose) + balance` |
| Evaluator-Optimizer (P6) | `sdk-llm/eval_optimizer.py` | `(generate + critique).loop(approved)`, typed verdict |
| Mixture-of-Agents (P7) | `sdk-llm/mixture_of_agents.py` | layered `gather_all + synth + gather_all + synth` |
| Router (P8) | `sdk-llm/router.py` | `branch(decision, cases)` |
| Orchestrator-Workers (P9) | `sdk-llm/orchestrator_workers.py` | `plan + work + synthesize`, runtime-sized fan-out |
| Handoff / Swarm (P10) | `sdk-llm/swarm.py` | `branch(by station)` inside `.loop` |
| Group Chat (P11) | `sdk-llm/group_chat.py` | `branch(manager decision)` inside `.loop` |
| Hierarchical Teams (P12) | `sdk-llm/hierarchical.py` | `embed` a research sub-flow as one node |
| Blackboard (P13) | `sdk-llm/blackboard.py` | `blackboard(*rules)`, author-written `when` |
| Contract-Net (P14) | `sdk-llm/contract_net.py` | `blackboard` + `AuctionSelect` policy |
| Reflection (P15) | `sdk-llm/reflection.py` | `revise.loop(good_enough)`, critic folded in |
| Debate (P16) | `sdk-llm/debate.py` | `((pro * con) + judge).loop(rounds)` |
| mixed pipeline | `sdk-llm/mixed.py` | LLM extract + mechanical compute + LLM phrase, typed structured output |
| SDK injection | `sdk-llm/injection.py` | pydantic-ai and langchain over one `LLM` seam, injected by name |
