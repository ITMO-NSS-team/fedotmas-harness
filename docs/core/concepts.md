# Concepts

fedotmas runs multi-agent systems on one small engine and gives you two ways to author for it.
This page is the shared model and the map; the [engine](engine.md), [flow](flow.md), and [blackboard](blackboard.md) pages are the detail.

## One engine

State lives in one shared place, the **store**, as a growing list of tagged **facts**.
Nodes do not call each other.
Each node watches the store, declares when it is ready, and writes new facts back.
The engine runs in rounds called **supersteps**: it takes one snapshot, asks every node whether it is ready, runs the ready ones together, then commits all their writes at once.
Nodes in one superstep see the same snapshot and none sees the others' writes until the next round.

That is the whole runtime.
There are no edges and no scheduler wiring: the topology is implied by which facts a node reads and which it writes.
The [engine page](engine.md) makes the pieces (Fact, Store, Node, Result, triggers, policy, terminate) concrete.

## Two surfaces

Everything above the engine is a way to produce nodes for it.
There are two authoring surfaces, picked by the shape of the work.

The **[flow](flow.md)** surface is a typed arrow.
A `Flow[A, B]` is a fragment from an input of type `A` to an output of type `B`.
You build small atoms (`action` wraps a function) and compose them with a handful of operators (`+`, `gather`, `branch`, `.loop`, `nest`).
The composition is checkable before anything runs.
Use it when the topology is known as you write it: a chain, a fan-out, a router, a refinement loop.

The **[blackboard](blackboard.md)** surface is for opportunistic work.
Rules self-activate when the store happens to satisfy them, in no fixed order.
There is no `A -> B` shape, so there is nothing to type.
Use it when the width is decided at runtime, the next speaker is chosen by a manager, work is handed off dynamically, or a task is auctioned to the best bidder.

`nest` is the seam between them: a goal-terminating blackboard (or a whole sub-flow) becomes one typed node of a flow, its interior opaque, its boundary checked.

## When a flow is the wrong shape

A flow is the dataflow subset of what the runtime can do, and within that subset it gives you static checking the raw runtime cannot.
Some systems do not have a fixed topology, and forcing them into an arrow would be a category error.
They live on the blackboard surface (authored triggers, optionally a runtime policy that picks who fires), where there is no shape to derive and so nothing to type.
When such a system converges on a goal, `nest` brings its result back across the boundary as a single typed node.
Reach for a flow where the shape is fixed, reach for the blackboard where order is emergent, and let `nest` be the seam between them.

## Why the types

The flow types are a design-time contract.
Runtime values are `Any` at execution time; the types live only at design time, checked by `ty` (or mypy) before you run.
They buy correctness by construction.
An unreduced `gather` is a `list` with nowhere to go that the next stage must consume; a loop over a non-state-preserving body is a receiver that does not match `Flow[A, A]`.
Each of these is a static error at the line you wrote, not a wrong fact discovered mid-run.

The payoff scales past hand-written systems.
A typed Python arrow algebra is a small, prunable search space and a far better target for a program that generates systems than a freeform diagram.
The same property that catches your mistake prunes a generator's.
