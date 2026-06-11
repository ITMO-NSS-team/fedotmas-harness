"""The arrow surface: typed dataflow fragments that compile to an engine System.

A Flow[A, B] is a fragment from an input of type A to an output of type B. Flows compose into
whole systems: + is sequence, * is the binary parallel product, gather_all its n-ary form, branch
routes to one case by a label, .loop iterates a state-preserving flow, nest runs a sub-system
as one opaque node. The type parameters make each stitch checkable: a + b only type-checks when
b accepts what a produces, so an unjoined parallel (a tuple the next stage must consume) becomes
a type error, not a runtime footgun.

This module is the algebra only. The leaves that fill it, action (code) and agent (a prompt
over the LLM seam), live in atoms; the rule surface in blackboard. Composition is lazy: a
Flow allocates fact tags and nodes only at .system(), so the same fragment can be reused and
nested. An LLM backend bound at .system() / .run() becomes the default for every LLM node
that did not bind its own; an unbound node fails there, at compile time, not mid-run.

Where the algebra takes a predicate or a selector, it also takes a declarative form that a
program can emit as data: .loop(until=) accepts a state key or a Condition next to a callable,
and branch(select=) accepts a state key next to a callable or a label-producing flow (an
agent with labels=).

One event-wave caveat: a join (* or gather_all) reads the latest version of each source, and
re-fires as soon as any source gains one. In a single-shot run that is exactly "fire once when
all arrive", but under mid-run commits with branches of unequal length a join can emit a mixed
pair (one branch's new value, the other's stale one) before the slower branch lands. Waves are
not yet aligned per join; that needs an epoch notion the engine does not have.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Generic, Literal, TypeVar

from pydantic import BaseModel, model_validator

from fedotmas.engine.contract import Fact, Node, Result, Status, View
from fedotmas.engine.executor import ReactiveExecutor
from fedotmas.engine.node import as_node
from fedotmas.engine.report import Run, StepReport
from fedotmas.engine.store import Store
from fedotmas.engine.system import System
from fedotmas.engine.terminate import Budget, Goal, Terminate, any_of

if TYPE_CHECKING:
    from fedotmas.engine.policy import Policy
    from fedotmas.sdk.atoms import LLM
    from fedotmas.sdk.blackboard import Board

A = TypeVar("A")
B = TypeVar("B")
C = TypeVar("C")


def _pick(state: Any, key: str) -> Any:
    if isinstance(state, dict):
        return state.get(key)
    return getattr(state, key, None)


class Condition(BaseModel):
    """A declarative predicate over one key of the state: data, not code, so a program that
    emits systems can express a stop or routing condition without writing a callable. `key`
    is looked up in the state (dict key or attribute, absent reads as None), `op` compares it
    to `value`. The default op is truthy, so Condition(key="approved") means state["approved"].
    """

    key: str
    op: Literal["truthy", "not", "eq", "ne", "gt", "lt", "gte", "lte", "exists"] = (
        "truthy"
    )
    value: Any = None

    @model_validator(mode="after")
    def _value_matches_op(self) -> Condition:
        if self.op in ("gt", "lt", "gte", "lte") and self.value is None:
            raise ValueError(
                f"Condition(key={self.key!r}, op={self.op!r}): an ordered comparison "
                "needs value="
            )
        if self.op in ("truthy", "not", "exists") and self.value is not None:
            raise ValueError(
                f"Condition(key={self.key!r}, op={self.op!r}): {self.op} does not "
                "compare, drop value="
            )
        return self

    def check(self, state: Any) -> bool:
        if self.op == "exists":
            return (
                self.key in state
                if isinstance(state, dict)
                else hasattr(state, self.key)
            )
        v = _pick(state, self.key)
        if self.op == "truthy":
            return bool(v)
        if self.op == "not":
            return not v
        if self.op == "eq":
            return v == self.value
        if self.op == "ne":
            return v != self.value
        if v is None:
            raise ValueError(
                f"Condition(key={self.key!r}, op={self.op!r}): the state has no "
                f"{self.key!r} to compare"
            )
        if self.op == "gt":
            return v > self.value
        if self.op == "lt":
            return v < self.value
        if self.op == "gte":
            return v >= self.value
        return v <= self.value


def _as_predicate(
    until: Callable[[Any], bool] | Condition | str,
) -> Callable[[Any], bool]:
    if isinstance(until, str):
        until = Condition(key=until)
    if isinstance(until, Condition):
        return until.check
    return until


@dataclass
class _Ctx:
    llm: LLM | None = None
    n: int = 0

    def fresh(self, hint: str) -> str:
        self.n += 1
        return f"{hint}#{self.n}"


def _gather_node(name: str, srcs: list[str], out: str) -> Node:
    async def invoke(input: Any, view: View) -> Result:
        value = tuple(view.value(s) for s in srcs)
        return Result(writes=[Fact(tag=out, value=value)])

    return as_node(invoke, name=name, reads=" ".join(srcs))


def _collect_node(name: str, srcs: list[str], out: str) -> Node:
    async def invoke(input: Any, view: View) -> Result:
        return Result(writes=[Fact(tag=out, value=[view.value(s) for s in srcs])])

    return as_node(invoke, name=name, reads=" ".join(srcs))


def _alias_node(src: str, out: str, name: str | None = None) -> Node:
    async def invoke(input: Any, view: View) -> Result:
        return Result(writes=[Fact(tag=out, value=view.value(src))])

    return as_node(invoke, name=name or f"alias:{out}", reads=src)


def _inner_guard(run: Run, out: str, what: str) -> None:
    """Surface an inner run's failure as this node's failure, so the outer engine records it
    as an error fact instead of silently writing None."""
    if run.status is Status.ERROR:
        msgs = "; ".join(
            f"{e.producer}: {e.value}" for s in run.steps for e in s.errors
        )
        raise RuntimeError(f"{what}: inner system failed ({msgs})")
    if not run.view.exists(out):
        raise RuntimeError(
            f"{what}: inner system stopped ({run.reason}) before producing {out!r}"
        )


@dataclass
class Outcome:
    """The outcome of a run surface (Flow.run, Board.run): the engine Run plus the out tag,
    read back as one object. `value` is the produced output (None if the run never reached
    it), `ok` is "finished clean and produced the output", and `reason` says how the run
    ended: "goal" (output produced), "error" (a node failed, see `errors`), "budget" (step
    cap hit first), or "stalled" (the system went quiet without producing the output: a
    wiring gap). Under halt_on_error=False a run can end reason "goal" with `errors`
    non-empty; `ok` stays False, it never overlooks an error.
    """

    run: Run
    out: str

    @property
    def view(self) -> View:
        return self.run.view

    @property
    def steps(self) -> list[StepReport]:
        return self.run.steps

    @property
    def value(self) -> Any:
        return self.run.view.value(self.out)

    @property
    def errors(self) -> list[Fact]:
        return [e for s in self.run.steps for e in s.errors]

    @property
    def ok(self) -> bool:
        return self.run.status is Status.OK and self.run.view.exists(self.out)

    @property
    def reason(self) -> Literal["goal", "error", "budget", "stalled"]:
        if self.run.reason == "error":
            return "error"
        if self.run.view.exists(self.out):
            return "goal"
        return "stalled" if self.run.reason == "quiescence" else "budget"

    def __repr__(self) -> str:
        value = repr(self.value)
        if len(value) > 120:
            value = value[:117] + "..."
        return f"Outcome(ok={self.ok}, reason={self.reason!r}, value={value})"


class Flow(Generic[A, B]):
    """A typed dataflow fragment from input A to output B. Make atoms with action (code) or
    agent (LLM), then compose: + is sequence, * and gather_all are parallel, branch routes
    by label, .loop iterates, nest wraps a whole sub-system as one node. `.system(entry, out)`
    compiles the fragment to an engine System; `.run(value)` compiles and executes it in one
    call. The type parameters check each stitch: a + b only type-checks when b accepts what a
    produces.
    """

    def _build(self, ctx: _Ctx, entry: str) -> tuple[list[Node], str]:
        raise NotImplementedError

    def system(self, *, entry: str, out: str, llm: LLM | None = None) -> System:
        """Compile to a runnable System. `llm` becomes the default backend for every LLM node
        that did not bind its own; a node with no backend at all fails here, not mid-run."""
        ctx = _Ctx(llm=llm)
        nodes, last = self._build(ctx, entry)
        if last != out:
            nodes = [*nodes, _alias_node(last, out)]
        return System(nodes)

    def _prepare(self, llm: LLM | None, budget: int | None) -> tuple[System, Terminate]:
        system = self.system(entry="in", out="out", llm=llm)
        terminate: Terminate = Goal(lambda v: v.exists("out"))
        if budget is not None:
            terminate = terminate | Budget(budget)
        return system, terminate

    async def run(
        self,
        value: A,
        *,
        llm: LLM | None = None,
        budget: int | None = 100,
        policy: Policy | None = None,
        halt_on_error: bool = True,
    ) -> Outcome:
        """Compile and execute the flow on one input. The store, the seed fact, and the
        terminate condition (output produced, capped by `budget` supersteps; the default 100
        is a runaway guard, None lifts the cap) are derived, so the caller holds no tags.
        `halt_on_error=False` keeps the run going past a failed node; the error still lands
        in `.errors` and `.ok` stays False. Returns an Outcome: `.value`, `.ok`, `.reason`,
        `.errors`, and the full `.steps` trace.
        """
        system, terminate = self._prepare(llm, budget)
        run = await ReactiveExecutor(halt_on_error=halt_on_error).run(
            system,
            Store(),
            seed=[Fact(tag="in", value=value)],
            terminate=terminate,
            policy=policy,
        )
        return Outcome(run, "out")

    async def stream(
        self,
        value: A,
        *,
        llm: LLM | None = None,
        budget: int | None = 100,
        policy: Policy | None = None,
        halt_on_error: bool = True,
    ) -> AsyncIterator[StepReport]:
        """The streaming form of .run: yields each StepReport as the run unfolds."""
        system, terminate = self._prepare(llm, budget)
        async for report in ReactiveExecutor(halt_on_error=halt_on_error).stream(
            system,
            Store(),
            seed=[Fact(tag="in", value=value)],
            terminate=terminate,
            policy=policy,
        ):
            yield report

    def __add__(self, other: Flow[B, C]) -> Flow[A, C]:
        return _Seq(self, other)

    def __mul__(self, other: Flow[A, C]) -> Flow[A, tuple[B, C]]:
        return _Par(self, other)

    def then(self, other: Flow[B, C]) -> Flow[A, C]:
        return _Seq(self, other)

    def par(self, other: Flow[A, C]) -> Flow[A, tuple[B, C]]:
        return _Par(self, other)

    def loop(
        self: Flow[A, A],
        until: Callable[[A], bool] | Condition | str,
        *,
        budget: int | None = 100,
    ) -> Flow[A, A]:
        """Iterate the flow, feeding each round's output in as the next round's input, until
        `until` clears. `until` is a callable over the state, a Condition, or a state key (stop
        when state[key] is truthy). Each round runs the body in its own inner store as one
        outer superstep, so rounds are capped by the outer budget but a round itself is not;
        `budget` caps the supersteps inside one round (default 100, None lifts it)."""
        return _Loop(self, _as_predicate(until), budget)


class _Seq(Flow[Any, Any]):
    def __init__(self, left: Flow[Any, Any], right: Flow[Any, Any]) -> None:
        self._left = left
        self._right = right

    def _build(self, ctx: _Ctx, entry: str) -> tuple[list[Node], str]:
        la, lout = self._left._build(ctx, entry)
        ra, rout = self._right._build(ctx, lout)
        return [*la, *ra], rout


class _Par(Flow[Any, Any]):
    def __init__(self, left: Flow[Any, Any], right: Flow[Any, Any]) -> None:
        self._left = left
        self._right = right

    def _build(self, ctx: _Ctx, entry: str) -> tuple[list[Node], str]:
        la, lout = self._left._build(ctx, entry)
        ra, rout = self._right._build(ctx, entry)
        out = ctx.fresh("par")
        return [*la, *ra, _gather_node(out, [lout, rout], out)], out


class _Loop(Flow[Any, Any]):
    def __init__(
        self, body: Flow[Any, Any], until: Callable[[Any], bool], budget: int | None
    ) -> None:
        self._body = body
        self._until = until
        self._budget = budget

    def _build(self, ctx: _Ctx, entry: str) -> tuple[list[Node], str]:
        name = ctx.fresh("loop")
        out = name
        state = f"{name}:s"
        body_in, body_out = f"{name}:in", f"{name}:out"
        body = self._body.system(entry=body_in, out=body_out, llm=ctx.llm)
        until = self._until
        round_term: Terminate = Goal(lambda v: v.exists(body_out))
        if self._budget is not None:
            round_term = any_of(round_term, Budget(self._budget))

        async def iterate(input: Any, view: View) -> Result:
            seen = view.query(f"{state}:*")
            src = seen[-1].value if seen else (view.value(entry) if entry else None)
            inner = Store()
            run = await ReactiveExecutor().run(
                body,
                inner,
                seed=[Fact(tag=body_in, value=src)],
                terminate=round_term,
            )
            _inner_guard(run, body_out, f"loop {name!r} round {len(seen) + 1}")
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

        nodes = [
            as_node(
                iterate,
                name=f"{name}:iter",
                reads=f"{state}:*",
                trigger=iterate_trigger,
            ),
            as_node(
                finish, name=f"{name}:done", reads=f"{state}:*", trigger=finish_trigger
            ),
        ]
        return nodes, out


class _Branch(Flow[Any, Any]):
    def __init__(
        self,
        select: Flow[Any, Any] | Callable[[Any], str],
        cases: dict[str, Flow[Any, Any]],
    ) -> None:
        self._select = select
        self._cases = cases

    def _build(self, ctx: _Ctx, entry: str) -> tuple[list[Node], str]:
        name = ctx.fresh("branch")
        out = name
        ins = {k: f"{name}:in:{k}" for k in self._cases}
        select = self._select
        nodes: list[Node] = []

        label_tag = ""
        classify: Callable[[Any], str] | None = None
        if isinstance(select, Flow):
            sel_nodes, label_tag = select._build(ctx, entry)
            nodes.extend(sel_nodes)
            route_reads = label_tag
        else:
            classify = select
            route_reads = entry

        async def route(input: Any, view: View) -> Result:
            value = view.value(entry) if entry else None
            key = classify(value) if classify is not None else view.value(label_tag)
            if key not in ins:
                raise ValueError(
                    f"branch {name!r} got label {key!r}, not one of {sorted(ins)}"
                )
            return Result(writes=[Fact(tag=ins[key], value=value)])

        nodes.append(as_node(route, name=f"{name}:route", reads=route_reads))
        for k, case in self._cases.items():
            case_nodes, case_out = case._build(ctx, ins[k])
            nodes.extend(case_nodes)
            nodes.append(_alias_node(case_out, out, name=f"{name}:join:{k}"))
        return nodes, out


def branch(
    select: Flow[A, str] | Callable[[A], str] | str, cases: dict[str, Flow[A, B]]
) -> Flow[A, B]:
    """Route the input to exactly one case by a label, then merge back to one output. `select`
    is a python callable A -> label, a state key (route by state[key], the declarative form),
    or a label-producing flow (an agent with labels=, when the route is the model's choice;
    an extra router step). All cases share input and output types, so the whole branch stays
    one typed arrow Flow[A, B].
    """
    if isinstance(select, str):
        key = select
        select = lambda state: _pick(state, key)  # noqa: E731
    return _Branch(select, cases)


class _GatherAll(Flow[Any, Any]):
    def __init__(self, flows: tuple[Flow[Any, Any], ...]) -> None:
        self._flows = flows

    def _build(self, ctx: _Ctx, entry: str) -> tuple[list[Node], str]:
        out = ctx.fresh("gather_all")
        nodes: list[Node] = []
        srcs: list[str] = []
        for flow in self._flows:
            built, fout = flow._build(ctx, entry)
            nodes.extend(built)
            srcs.append(fout)
        return [*nodes, _collect_node(out, srcs, out)], out


def gather_all(*flows: Flow[A, B]) -> Flow[A, list[B]]:
    """Run several flows on the same input in parallel and collect their outputs into a list,
    joined when all complete. The n-ary form of *; follow it with a reducer (e.g. + majority)
    to fold the list into one value. Named gather_all, not gather, so it never shadows
    asyncio.gather.
    """
    if not flows:
        raise ValueError("gather_all needs at least one flow")
    return _GatherAll(flows)


class _Nest(Flow[A, B]):
    def __init__(
        self,
        target: System | Flow[A, B] | Board,
        *,
        entry: str,
        out: str,
        until: Terminate | None,
        budget: int | None,
    ) -> None:
        self._target = target
        self._entry = entry
        self._out = out
        self._until = until
        self._budget = budget

    def _build(self, ctx: _Ctx, entry: str) -> tuple[list[Node], str]:
        name = ctx.fresh("nest")
        inner_entry, inner_out = self._entry, self._out
        if isinstance(self._target, Flow):
            system = self._target.system(entry=inner_entry, out=inner_out, llm=ctx.llm)
        elif isinstance(self._target, System):
            system = self._target
        else:  # a Board: compile with the flow's default llm as the fallback backend
            system = self._target.compile(ctx.llm)
        until = self._until or Goal(lambda v: v.exists(inner_out))
        if self._budget is not None:
            until = any_of(until, Budget(self._budget))

        async def invoke(input: Any, view: View) -> Result:
            inner = Store()
            run = await ReactiveExecutor().run(
                system,
                inner,
                seed=[
                    Fact(tag=inner_entry, value=view.value(entry) if entry else None)
                ],
                terminate=until,
            )
            _inner_guard(run, inner_out, f"nest {name!r}")
            return Result(writes=[Fact(tag=name, value=run.view.value(inner_out))])

        return [as_node(invoke, name=name, reads=entry)], name


def nest(
    target: System | Flow[A, B] | Board,
    *,
    entry: str,
    out: str,
    until: Terminate | None = None,
    budget: int | None = 100,
) -> Flow[A, B]:
    """Run a whole sub-system as one typed arrow node: its own inner store, run to a goal,
    one fact out. The boundary is typed and composes; the interior stays opaque. This is
    how a goal-terminating Board (the blackboard surface) enters the arrow world, and how a
    flow nests another flow as an isolated unit. A Flow or Board target picks up the outer
    flow's default llm as its fallback backend; a System is already compiled, so the default
    does not reach inside it. The inner run is the outer node's single superstep, so the
    outer budget cannot interrupt it; `budget` caps the inner supersteps instead (the default
    100 is a runaway guard, None lifts it). The inner run always halts on its first error and
    the failure surfaces as this node's error fact; the outer halt_on_error then decides
    whether the rest of the system continues. Named nest, not embed, to avoid the embeddings
    reading.
    """
    return _Nest(target, entry=entry, out=out, until=until, budget=budget)
