# Pattern examples

Every example runs the **same** `ReactiveExecutor` over the **same** `Store` + `Agent`
contract. Nothing in the engine changes between patterns, only the agents, their
triggers, the `Policy`, and the `Terminate` condition differ. That is the universality
claim, checked on running code.

Run any one: `uv run python examples/<name>.py` (each streams its superstep trace).

| Pattern | File | Engine mechanism exercised |
|---|---|---|
| Prompt Chaining (P1) | `prompt_chaining.py` | seq via fact dependency, edge-trigger dedup |
| Sectioning (P2) | `sectioning.py` | fan-out + join (count-gated trigger) |
| Self-Consistency (P3) | `voting.py` | replicas keyed by identity + majority aggregator |
| Ensemble Voting (P4) | `voting.py` | same shape as P3, distinct agents |
| DAG (P5) | `dag.py` | diamond dependency, join on two upstreams |
| Evaluator-Optimizer (P6) | `eval_optimizer.py` | loop until goal, generator/critic alternation |
| Mixture-of-Agents (P7) | `mixture_of_agents.py` | layered parallel with aggregation between layers |
| Router (P8) | `router.py` | label fact activates exactly one target |
| Orchestrator-Workers (P9) | `orchestrator_workers.py` | runtime-decided width, batch-mapped worker |
| Handoff / Swarm (P10) | `swarm.py` | active-fact handoff, loop until done |
| Group Chat (P11) | `group_chat.py` | manager/speaker turns over a shared transcript |
| Hierarchical Teams (P12) | `hierarchical.py` | a sub-System wrapped as one agent (nesting) |
| Blackboard (P13) | `blackboard.py` | author-written triggers, self-activation, goal stop |
| Contract-Net (P14) | `contract_net.py` | `AuctionSelect` Policy picks the winning bidder |
| Reflection (P15) | `reflection.py` | single agent self-revises (critic folded in) |
| Debate (P16) | `debate.py` | parallel rounds judged in a loop, transcript accrues |
