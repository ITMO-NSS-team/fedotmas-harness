"""The arrow surface: typed dataflow fragments that compile to an engine System.

A Flow[A, B] is a fragment from an input of type A to an output of type B. Flows compose into
whole systems: + is sequence, gather runs branches in parallel and lists their outputs, branch
routes to one case by a label, .loop iterates a state-preserving flow, .into and .merge thread
a dict state past a step, nest runs a sub-system as one opaque node. The type parameters make each stitch checkable: a + b only type-checks when
b accepts what a produces, so an unjoined parallel (a list the next stage must consume) becomes
a type error, not a runtime footgun.

This package is the algebra only. The leaves that fill it, action (code) and agent (a prompt
over the LLM seam), live in atoms; the rule surface in blackboard. Composition is lazy: a
Flow allocates fact tags and nodes only at .system(), so the same fragment can be reused and
nested. An LLM backend bound at .system() / .run() becomes the default for every LLM node
that did not bind its own; an unbound node fails there, at compile time, not mid-run.

Where the algebra takes a predicate or a selector, it also takes a declarative form that a
program can emit as data: .loop(until=) accepts a state key or a Condition next to a callable,
and branch(select=) accepts a state key next to a callable or a label-producing flow (an
agent with labels=).

One event-wave caveat: a join (gather) reads the latest version of each source, and
re-fires as soon as any source gains one. In a single-shot run that is exactly "fire once when
all arrive", but under mid-run commits with branches of unequal length a join can emit a mixed
list (one branch's new value, the other's stale one) before the slower branch lands. Waves are
not yet aligned per join; that needs an epoch notion the engine does not have.

Inside, the package splits by layer: this __init__ is the public surface; the operator
algebra lives in _algebra, the declarative Condition in _condition, the run Outcome in
_outcome, and the node factories everything compiles to in _nodes.
"""

from fedotmas.sdk.flow._algebra import Flow, branch, gather, nest
from fedotmas.sdk.flow._condition import Condition
from fedotmas.sdk.flow._outcome import Outcome, RunError

__all__ = ["Condition", "Flow", "Outcome", "RunError", "branch", "gather", "nest"]
