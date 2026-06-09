"""The edge surface as typed arrows. A Flow[A, B] is a dataflow fragment from an input
of type A to an output of type B that compiles to an engine System.

Flows compose into whole MAS: + is sequence, * is the binary parallel product, gather is
its n-ary form, branch routes to one case by a label, .loop iterates a state-preserving
flow, embed runs a sub-system as one opaque node. The type parameters make the stitch
checkable: a + b only type-checks when b accepts what a produces, so an unjoined parallel
(a tuple output the next stage must consume) becomes a type error, not a runtime footgun.

This module is model-free: action is the only atom here, mechanical. The LLM atoms (agent,
decision) live in llm; the rule surface in rules. Composition is lazy, a Flow only allocates
fact tags and agents at .system(), so the same fragment can be reused and nested.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Generic, TypeVar

from fedotmas.adapters import as_agent
from fedotmas.engine.contract import Agent, Fact, Result, View
from fedotmas.engine.executor import ReactiveExecutor
from fedotmas.engine.store import Store
from fedotmas.engine.system import System
from fedotmas.engine.terminate import Goal, Terminate

A = TypeVar("A")
B = TypeVar("B")
C = TypeVar("C")

ActionFn = Callable[[A, View], Awaitable[B]]


@dataclass
class _Ctx:
    n: int = 0

    def fresh(self, hint: str) -> str:
        self.n += 1
        return f"{hint}#{self.n}"


def _action_agent(name: str, fn: ActionFn[Any, Any], reads: str, out: str) -> Agent:
    async def invoke(input: Any, view: View) -> Result:
        value = await fn(view.value(reads) if reads else None, view)
        return Result(writes=[Fact(tag=out, value=value)])

    return as_agent(invoke, name=name, reads=reads)


def _gather_agent(name: str, srcs: list[str], out: str) -> Agent:
    async def invoke(input: Any, view: View) -> Result:
        value = tuple(view.value(s) for s in srcs)
        return Result(writes=[Fact(tag=out, value=value)])

    return as_agent(invoke, name=name, trigger=lambda v: all(v.exists(s) for s in srcs))


def _collect_agent(name: str, srcs: list[str], out: str) -> Agent:
    async def invoke(input: Any, view: View) -> Result:
        return Result(writes=[Fact(tag=out, value=[view.value(s) for s in srcs])])

    return as_agent(invoke, name=name, trigger=lambda v: all(v.exists(s) for s in srcs))


def _alias_agent(src: str, out: str, name: str | None = None) -> Agent:
    async def invoke(input: Any, view: View) -> Result:
        return Result(writes=[Fact(tag=out, value=view.value(src))])

    return as_agent(invoke, name=name or f"alias:{out}", reads=src)


class Flow(Generic[A, B]):
    """A typed dataflow fragment from input A to output B. Make atoms with action (or agent,
    decision from llm), then compose: + is sequence, * and gather are parallel, branch routes
    by label, .loop iterates, embed nests a whole sub-system as one node. `.system(entry, out)`
    compiles the fragment to an engine System. The type parameters check each stitch: a + b
    only type-checks when b accepts what a produces.
    """

    def _build(self, ctx: _Ctx, entry: str) -> tuple[list[Agent], str]:
        raise NotImplementedError

    def system(self, *, entry: str, out: str) -> System:
        ctx = _Ctx()
        agents, last = self._build(ctx, entry)
        if last != out:
            agents = [*agents, _alias_agent(last, out)]
        return System(agents)

    def __add__(self, other: Flow[B, C]) -> Flow[A, C]:
        return _Seq(self, other)

    def __mul__(self, other: Flow[A, C]) -> Flow[A, tuple[B, C]]:
        return _Par(self, other)

    def then(self, other: Flow[B, C]) -> Flow[A, C]:
        return _Seq(self, other)

    def par(self, other: Flow[A, C]) -> Flow[A, tuple[B, C]]:
        return _Par(self, other)

    def loop(self: Flow[A, A], until: Callable[[A], bool]) -> Flow[A, A]:
        return _Loop(self, until)


class _Action(Flow[A, B]):
    def __init__(self, name: str, fn: ActionFn[A, B]) -> None:
        self._name = name
        self._fn = fn

    def _build(self, ctx: _Ctx, entry: str) -> tuple[list[Agent], str]:
        out = ctx.fresh(self._name)
        return [_action_agent(out, self._fn, entry, out)], out


class _Seq(Flow[Any, Any]):
    def __init__(self, left: Flow[Any, Any], right: Flow[Any, Any]) -> None:
        self._left = left
        self._right = right

    def _build(self, ctx: _Ctx, entry: str) -> tuple[list[Agent], str]:
        la, lout = self._left._build(ctx, entry)
        ra, rout = self._right._build(ctx, lout)
        return [*la, *ra], rout


class _Par(Flow[Any, Any]):
    def __init__(self, left: Flow[Any, Any], right: Flow[Any, Any]) -> None:
        self._left = left
        self._right = right

    def _build(self, ctx: _Ctx, entry: str) -> tuple[list[Agent], str]:
        la, lout = self._left._build(ctx, entry)
        ra, rout = self._right._build(ctx, entry)
        out = ctx.fresh("par")
        return [*la, *ra, _gather_agent(out, [lout, rout], out)], out


class _Loop(Flow[Any, Any]):
    def __init__(self, body: Flow[Any, Any], until: Callable[[Any], bool]) -> None:
        self._body = body
        self._until = until

    def _build(self, ctx: _Ctx, entry: str) -> tuple[list[Agent], str]:
        name = ctx.fresh("loop")
        out = name
        state = f"{name}:s"
        body_in, body_out = f"{name}:in", f"{name}:out"
        body = self._body.system(entry=body_in, out=body_out)
        until = self._until

        async def iterate(input: Any, view: View) -> Result:
            seen = view.query(f"{state}:*")
            src = seen[-1].value if seen else (view.value(entry) if entry else None)
            inner = Store()
            run = await ReactiveExecutor().run(
                body,
                inner,
                seed=[Fact(tag=body_in, value=src)],
                terminate=Goal(lambda v: v.exists(body_out)),
            )
            n = len(seen) + 1
            return Result(
                writes=[Fact(tag=f"{state}:{n}", value=run.view.value(body_out))]
            )

        def iterate_trigger(view: View) -> bool:
            seen = view.query(f"{state}:*")
            if not seen:
                return view.exists(entry) if entry else True
            return not until(seen[-1].value)

        async def finish(input: Any, view: View) -> Result:
            return Result(
                writes=[Fact(tag=out, value=view.query(f"{state}:*")[-1].value)]
            )

        def finish_trigger(view: View) -> bool:
            seen = view.query(f"{state}:*")
            return bool(seen) and until(seen[-1].value) and not view.exists(out)

        agents = [
            as_agent(
                iterate,
                name=f"{name}:iter",
                reads=f"{state}:*",
                trigger=iterate_trigger,
            ),
            as_agent(
                finish, name=f"{name}:done", reads=f"{state}:*", trigger=finish_trigger
            ),
        ]
        return agents, out


class _Branch(Flow[Any, Any]):
    def __init__(
        self,
        select: Flow[Any, Any] | Callable[[Any], str],
        cases: dict[str, Flow[Any, Any]],
    ) -> None:
        self._select = select
        self._cases = cases

    def _build(self, ctx: _Ctx, entry: str) -> tuple[list[Agent], str]:
        name = ctx.fresh("branch")
        out = name
        ins = {k: f"{name}:in:{k}" for k in self._cases}
        select = self._select
        agents: list[Agent] = []

        label_tag = ""
        classify: Callable[[Any], str] | None = None
        if isinstance(select, Flow):
            sel_agents, label_tag = select._build(ctx, entry)
            agents.extend(sel_agents)
            route_reads = label_tag
        else:
            classify = select
            route_reads = entry

        async def route(input: Any, view: View) -> Result:
            value = view.value(entry) if entry else None
            key = classify(value) if classify is not None else view.value(label_tag)
            return Result(writes=[Fact(tag=ins[key], value=value)])

        agents.append(as_agent(route, name=f"{name}:route", reads=route_reads))
        for k, case in self._cases.items():
            case_agents, case_out = case._build(ctx, ins[k])
            agents.extend(case_agents)
            agents.append(_alias_agent(case_out, out, name=f"{name}:join:{k}"))
        return agents, out


def branch(
    select: Flow[A, str] | Callable[[A], str], cases: dict[str, Flow[A, B]]
) -> Flow[A, B]:
    """Route the input to exactly one case by a label, then merge back to one output. `select`
    is either a python callable A -> label (resolved in a single step) or a decision flow that
    produces the label (an extra router step). All cases share input and output types, so the
    whole branch stays one typed arrow Flow[A, B].
    """
    return _Branch(select, cases)


class _Gather(Flow[Any, Any]):
    def __init__(self, flows: tuple[Flow[Any, Any], ...]) -> None:
        self._flows = flows

    def _build(self, ctx: _Ctx, entry: str) -> tuple[list[Agent], str]:
        out = ctx.fresh("gather")
        agents: list[Agent] = []
        srcs: list[str] = []
        for flow in self._flows:
            fa, fout = flow._build(ctx, entry)
            agents.extend(fa)
            srcs.append(fout)
        return [*agents, _collect_agent(out, srcs, out)], out


def gather(*flows: Flow[A, B]) -> Flow[A, list[B]]:
    """Run several flows on the same input in parallel and collect their outputs into a list,
    joined when all complete. The n-ary form of *; follow it with a reducer (e.g. + majority)
    to fold the list into one value.
    """
    return _Gather(flows)


def action(fn: ActionFn[A, B]) -> Flow[A, B]:
    """Lift a plain async function (input, view) -> output into a Flow atom. The body is code
    and the types come from the signature; no model is involved. This is the model-free atom,
    the same arrow shape an agent has but mechanical, so the two compose without distinction.
    """
    return _Action(getattr(fn, "__name__", "action"), fn)


class _Embed(Flow[A, B]):
    def __init__(
        self, system: System, *, entry: str, out: str, until: Terminate | None
    ) -> None:
        self._system = system
        self._entry = entry
        self._out = out
        self._until = until

    def _build(self, ctx: _Ctx, entry: str) -> tuple[list[Agent], str]:
        name = ctx.fresh("embed")
        inner_entry, inner_out = self._entry, self._out
        until = self._until or Goal(lambda v: v.exists(inner_out))

        async def invoke(input: Any, view: View) -> Result:
            inner = Store()
            run = await ReactiveExecutor().run(
                self._system,
                inner,
                seed=[
                    Fact(tag=inner_entry, value=view.value(entry) if entry else None)
                ],
                terminate=until,
            )
            return Result(writes=[Fact(tag=name, value=run.view.value(inner_out))])

        return [as_agent(invoke, name=name, reads=entry)], name


def embed(
    target: System | Flow[A, B], *, entry: str, out: str, until: Terminate | None = None
) -> Flow[A, B]:
    """Run a whole sub-system as one typed arrow node: its own inner store, run to a goal,
    one fact out. The boundary is typed and composes; the interior stays opaque. This is
    how a goal-terminating blackboard (the rule surface) enters the arrow world, and how a
    flow nests another flow as an isolated unit.
    """
    system = target.system(entry=entry, out=out) if isinstance(target, Flow) else target
    return _Embed(system, entry=entry, out=out, until=until)
