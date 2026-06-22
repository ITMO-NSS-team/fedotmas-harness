# fedotmas-harness

Agent systems generation and harness. fedotmas runs multi-agent systems on one small engine
and gives you two ways to author for it: a typed **flow** of arrows for fixed-topology
dataflow, and a **blackboard** of self-activating rules for opportunistic work. Both compile
to the same superstep executor.

```python
from fedotmas import gather
from fedotmas_llm import agent

vote = gather(solver_a, solver_b, solver_c) + majority   # self-consistency
run = await vote.run("2 + 2", bind={"llm": some_llm})
```

## Where to go

- **[Concepts](concepts.md)** the shared model and how the two surfaces relate. Start here.
- **[Engine](engine.md)** the runtime: store, facts, nodes, supersteps, triggers, policy.
- **[Flow](flow.md)** the typed arrow surface: atoms, operators, loops, nesting.
- **[Blackboard](blackboard.md)** the rule surface for emergent, condition-driven activation.
- **[DSL](dsl.md)** the flow surface as a JSON document a program can emit.
