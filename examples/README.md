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
