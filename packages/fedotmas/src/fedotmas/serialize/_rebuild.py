from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from fedotmas._addressing import Branch, Loop
from fedotmas._condition import (
    CALLABLE,
    PRODUCE_ONCE,
    _pick,
    from_spec,
    state_predicate,
)
from fedotmas._inject import bind_async
from fedotmas.atoms import node_from_fn
from fedotmas.blackboard import Rule
from fedotmas.engine.contract import Kind, Node, View
from fedotmas.engine.system import System
from fedotmas.flow._nodes import (
    _alias_node,
    _collect_node,
    _into_node,
    _loop_finish_node,
    _loop_iterate_node,
    _merge_node,
    _nest_node,
    _route_node,
)
from fedotmas.serialize._blueprint import Blueprint, BlueprintNode


class ReconstructError(Exception):
    """from_blueprint could not rebuild a node: a body the blueprint cannot carry is missing
    from Deps, or the node is a hole the lacquer marked non-declarative (a callable until or
    select, an unknown kind)."""


@dataclass
class Deps:
    """What from_blueprint injects back into a rebuilt System. `bodies` fills the opaque code
    the blueprint cannot carry, keyed by node base name with any `#n` suffix stripped (an
    action's function, a code rule's fn). `bind` is the run-scoped resource map (e.g. an "llm"
    backend) for nodes that resolve one. The two are different by design: a body is the node's
    definition, a bind value a swappable resource."""

    bodies: dict[str, Callable[..., Any]] = field(default_factory=dict)
    bind: dict[str, Any] = field(default_factory=dict)


def from_blueprint(blueprint: Blueprint, deps: Deps) -> System:
    """Rebuild a runnable System from its declarative floor, the inverse of to_blueprint. Each
    node is reconstructed from its kind and params, with opaque bodies drawn from `deps` by
    name; a declarative control spec (state-key until/select) is recompiled to its predicate.
    The round-trip is the contract: `to_blueprint(from_blueprint(bp, deps)) == bp` and the
    rebuilt system runs to the same output. A node the blueprint could only mark (a callable
    until/select/when, an unknown kind) raises ReconstructError."""
    return System([_node(n, deps) for n in blueprint.nodes])


def _node(n: BlueprintNode, deps: Deps) -> Node:
    match n.kind:
        case Kind.ACTION:
            return node_from_fn(n.name, _body(n, deps), _join(n.reads), n.name)

        case Kind.GATHER:
            return _collect_node(n.name, list(n.params["srcs"]), n.name)

        case Kind.ALIAS | Kind.BRANCH_JOIN:
            return _alias_node(
                _first(n.reads), _first(n.writes), name=n.name, kind=n.kind
            )

        case Kind.INTO:
            return _into_node(
                n.name, n.params["state"], n.params["reply"], n.params["key"]
            )

        case Kind.MERGE:
            return _merge_node(n.name, n.params["state"], n.params["reply"])

        case Kind.NEST:
            return _nest(n, deps)
        case Kind.RULE:
            return _rule(n, deps)
        case Kind.BRANCH_ROUTE:
            return _route(n)
        case Kind.LOOP_ITER:
            return _loop_iter(n, deps)
        case Kind.LOOP_DONE:
            return _loop_done(n)

        case _:
            raise ReconstructError(f"node {n.name!r}: unknown kind {n.kind!r}")


def _body(n: BlueprintNode, deps: Deps) -> Callable[[Any, View], Any]:
    """The opaque body a node needs, drawn from Deps by its base name and adapted to the
    (input, view) contract. Missing is the named error."""
    fn = deps.bodies.get(n.base)
    if fn is None:
        raise ReconstructError(
            f"node {n.name!r}: no body for {n.base!r} in Deps.bodies"
        )
    return bind_async(fn)


def _nest(n: BlueprintNode, deps: Deps) -> Node:
    return _nest_node(
        n.name,
        system=_inner(n, deps),
        entry=_first(n.reads),
        inner_entry=n.params["entry"],
        inner_out=n.params["out"],
        budget=n.params.get("budget", 100),
    )


def _rule(n: BlueprintNode, deps: Deps) -> Node:
    rule = Rule(
        n.name,
        deps.bodies.get(n.base) or _missing(n.name),
        writes=_first(n.writes),
        reads=n.params.get("input", ""),
        when=_when(n.name, n.params.get("when")),
        meta=dict(n.meta),
    )
    return rule.to_node(deps.bind)


def _route(n: BlueprintNode) -> Node:
    addr = Branch.of(n.name)
    name = addr.base
    spec = n.params["select"]
    cases = list(n.params["cases"])
    if spec.get("by") != "state":
        raise ReconstructError(
            f"branch {name!r}: select by {spec.get('by')!r} is not declarative; only a "
            "state-key route rebuilds"
        )
    key = spec["key"]
    entry = _first(n.reads)
    ins = {k: addr.inlet(k) for k in cases}
    return _route_node(
        name,
        route_reads=entry,
        entry=entry,
        classify=lambda state, view: _pick(state, key),
        label_tag="",
        ins=ins,
        select_spec=spec,
        cases=cases,
    )


def _loop_iter(n: BlueprintNode, deps: Deps) -> Node:
    addr = Loop.of(n.name)
    fn, pred = _until(addr.base, n.params["until"])
    return _loop_iterate_node(
        addr.base,
        body=_inner(n, deps),
        body_in=addr.body_in,
        body_out=addr.body_out,
        entry=n.params["entry"],
        state=addr.state,
        until=fn,
        pred=pred,
        budget=n.params.get("budget", 100),
    )


def _loop_done(n: BlueprintNode) -> Node:
    addr = Loop.of(n.name)
    fn, pred = _until(addr.base, n.params["until"])
    return _loop_finish_node(
        addr.base, state=addr.state, out=_first(n.writes), until=fn, pred=pred
    )


def _when(name: str, spec: Any) -> Any:
    """A rule's trigger from its serialized when: the produce-once default (None), a rebuilt
    predicate, or the named error for an opaque callable the blueprint could not carry."""
    if spec is None or spec == PRODUCE_ONCE:
        return None
    if spec == CALLABLE:
        raise ReconstructError(
            f"rule {name!r}: when= was an opaque callable the blueprint cannot rebuild"
        )
    return from_spec(spec)


def _until(name: str, spec: Any) -> tuple[Callable[[Any, View], bool], Any]:
    """A loop's until callable plus its predicate, from the serialized spec; an opaque callable
    is the named error."""
    pred = from_spec(spec)
    if pred is None:
        raise ReconstructError(
            f"loop {name!r}: until= was an opaque callable the blueprint cannot rebuild"
        )
    return state_predicate(pred)


def _inner(n: BlueprintNode, deps: Deps) -> System:
    if n.inner is None:
        raise ReconstructError(f"node {n.name!r}: missing the inner system to rebuild")
    return from_blueprint(n.inner, deps)


def _missing(name: str) -> Callable[..., Any]:
    raise ReconstructError(f"rule {name!r}: no body named {name!r} in Deps.bodies")


def _first(tags: list[str]) -> str:
    return tags[0] if tags else ""


def _join(tags: list[str]) -> str:
    return " ".join(tags)
