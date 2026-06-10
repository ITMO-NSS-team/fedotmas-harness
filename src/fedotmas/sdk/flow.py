"""The arrow surface: typed dataflow fragments that compile to an engine System.

A Flow[A, B] is a fragment from an input of type A to an output of type B. Flows compose into
whole systems: + is sequence, * is the binary parallel product, gather_all its n-ary form, branch
routes to one case by a label, .loop iterates a state-preserving flow, nest runs a sub-system
as one opaque node. The type parameters make each stitch checkable: a + b only type-checks when
b accepts what a produces, so an unjoined parallel (a tuple the next stage must consume) becomes
a type error, not a runtime footgun.

This module is the algebra only. The leaves that fill it, action (model-free) and agent /
decision (over the LLM seam), live in atoms; the rule surface in blackboard. Composition is
lazy: a Flow allocates fact tags and agents only at .system(), so the same fragment can be
reused and nested. An LLM backend bound at .system() / .run() becomes the default for every
LLM node that did not bind its own; an unbound node fails there, at compile time, not mid-run.

Where the algebra takes a predicate or a selector, it also takes a declarative form that a
program can emit as data: .loop(until=) accepts a state key or a Cond next to a callable, and
branch(select=) accepts a state key next to a callable or a decision flow.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Generic, Literal, TypeVar

from pydantic import BaseModel

from fedotmas.adapters import as_agent
from fedotmas.engine.contract import Agent, Fact, Result, Status, View
from fedotmas.engine.executor import ReactiveExecutor
from fedotmas.engine.scheduler import Run, StepReport
from fedotmas.engine.store import Store
from fedotmas.engine.system import System
from fedotmas.engine.terminate import Budget, Goal, Terminate

if TYPE_CHECKING:
    from fedotmas.engine.policy import Policy
    from fedotmas.sdk.atoms import LLM

A = TypeVar("A")
B = TypeVar("B")
C = TypeVar("C")


def _pick(state: Any, key: str) -> Any:
    if isinstance(state, dict):
        return state.get(key)
    return getattr(state, key, None)


class Cond(BaseModel):
    """A declarative predicate over one key of the state: data, not code, so a program that
    emits systems can express a stop or routing condition without writing a callable. `key`
    is looked up in the state (dict key or attribute, absent reads as None), `op` compares it
    to `value`. The default op is truthy, so Cond(key="approved") means state["approved"].
    """

    key: str
    op: Literal["truthy", "not", "eq", "ne", "gte", "lte", "exists"] = "truthy"
    value: Any = None

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
        if self.op == "gte":
            return v >= self.value
        return v <= self.value


def _as_predicate(until: Callable[[Any], bool] | Cond | str) -> Callable[[Any], bool]:
    if isinstance(until, str):
        until = Cond(key=until)
    if isinstance(until, Cond):
        return until.check
    return until


@dataclass
class _Ctx:
    llm: LLM | None = None
    n: int = 0

    def fresh(self, hint: str) -> str:
        self.n += 1
        return f"{hint}#{self.n}"


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


def _inner_guard(run: Run, out: str, what: str) -> None:
    """Surface an inner run's failure as this node's failure, so the outer engine records it
    as an error fact instead of silently writing None."""
    if run.status is Status.ERROR:
        msgs = "; ".join(
            f"{e.producer}: {e.value}" for s in run.steps for e in s.errors
        )
        raise RuntimeError(f"{what}: inner system failed ({msgs})")
    if not run.view.exists(out):
        raise RuntimeError(f"{what}: inner system stalled before producing {out!r}")


@dataclass
class FlowRun:
    """The outcome of Flow.run: the engine Run plus the flow's out tag, read back as one
    object. `value` is the produced output (None if the run never reached it), `ok` is
    "finished and produced the output", and `reason` says how the run ended: "goal" (output
    produced), "error" (a node failed, see `errors`), "budget" (step cap hit first), or
    "stalled" (the system went quiet without producing the output: a wiring gap).
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
    def reason(self) -> str:
        if self.run.reason == "error":
            return "error"
        if self.run.view.exists(self.out):
            return "goal"
        return "stalled" if self.run.reason == "quiescence" else "budget"


class Flow(Generic[A, B]):
    """A typed dataflow fragment from input A to output B. Make atoms with action (or agent,
    decision from atoms), then compose: + is sequence, * and gather_all are parallel, branch routes
    by label, .loop iterates, nest wraps a whole sub-system as one node. `.system(entry, out)`
    compiles the fragment to an engine System; `.run(value)` compiles and executes it in one
    call. The type parameters check each stitch: a + b only type-checks when b accepts what a
    produces.
    """

    def _build(self, ctx: _Ctx, entry: str) -> tuple[list[Agent], str]:
        raise NotImplementedError

    def system(self, *, entry: str, out: str, llm: LLM | None = None) -> System:
        """Compile to a runnable System. `llm` becomes the default backend for every LLM node
        that did not bind its own; a node with no backend at all fails here, not mid-run."""
        ctx = _Ctx(llm=llm)
        agents, last = self._build(ctx, entry)
        if last != out:
            agents = [*agents, _alias_agent(last, out)]
        return System(agents)

    async def run(
        self,
        value: A,
        *,
        llm: LLM | None = None,
        budget: int | None = None,
        policy: Policy | None = None,
    ) -> FlowRun:
        """Compile and execute the flow on one input. The store, the seed fact, and the
        terminate condition (output produced, optionally capped by `budget` supersteps) are
        derived, so the caller holds no tags. Returns a FlowRun: `.value`, `.ok`, `.reason`,
        `.errors`, and the full `.steps` trace.
        """
        system = self.system(entry="in", out="out", llm=llm)
        terminate: Terminate = Goal(lambda v: v.exists("out"))
        if budget is not None:
            terminate = terminate | Budget(budget)
        store = Store()
        run = await ReactiveExecutor().run(
            system,
            store,
            seed=[Fact(tag="in", value=value)],
            terminate=terminate,
            policy=policy,
        )
        return FlowRun(run, "out")

    async def stream(
        self,
        value: A,
        *,
        llm: LLM | None = None,
        budget: int | None = None,
        policy: Policy | None = None,
    ) -> AsyncIterator[StepReport]:
        """The streaming form of .run: yields each StepReport as the run unfolds."""
        system = self.system(entry="in", out="out", llm=llm)
        terminate: Terminate = Goal(lambda v: v.exists("out"))
        if budget is not None:
            terminate = terminate | Budget(budget)
        async for report in ReactiveExecutor().stream(
            system, Store(), seed=[Fact(tag="in", value=value)], terminate=terminate
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

    def loop(self: Flow[A, A], until: Callable[[A], bool] | Cond | str) -> Flow[A, A]:
        """Iterate the flow, feeding each round's output in as the next round's input, until
        `until` clears. `until` is a callable over the state, a Cond, or a state key (stop
        when state[key] is truthy)."""
        return _Loop(self, _as_predicate(until))


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
        body = self._body.system(entry=body_in, out=body_out, llm=ctx.llm)
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
            if key not in ins:
                raise ValueError(
                    f"branch {name!r} got label {key!r}, not one of {sorted(ins)}"
                )
            return Result(writes=[Fact(tag=ins[key], value=value)])

        agents.append(as_agent(route, name=f"{name}:route", reads=route_reads))
        for k, case in self._cases.items():
            case_agents, case_out = case._build(ctx, ins[k])
            agents.extend(case_agents)
            agents.append(_alias_agent(case_out, out, name=f"{name}:join:{k}"))
        return agents, out


def branch(
    select: Flow[A, str] | Callable[[A], str] | str, cases: dict[str, Flow[A, B]]
) -> Flow[A, B]:
    """Route the input to exactly one case by a label, then merge back to one output. `select`
    is a python callable A -> label, a state key (route by state[key], the declarative form),
    or a decision flow that produces the label (an extra router step). All cases share input
    and output types, so the whole branch stays one typed arrow Flow[A, B].
    """
    if isinstance(select, str):
        key = select
        select = lambda state: _pick(state, key)  # noqa: E731
    return _Branch(select, cases)


class _GatherAll(Flow[Any, Any]):
    def __init__(self, flows: tuple[Flow[Any, Any], ...]) -> None:
        self._flows = flows

    def _build(self, ctx: _Ctx, entry: str) -> tuple[list[Agent], str]:
        out = ctx.fresh("gather_all")
        agents: list[Agent] = []
        srcs: list[str] = []
        for flow in self._flows:
            fa, fout = flow._build(ctx, entry)
            agents.extend(fa)
            srcs.append(fout)
        return [*agents, _collect_agent(out, srcs, out)], out


def gather_all(*flows: Flow[A, B]) -> Flow[A, list[B]]:
    """Run several flows on the same input in parallel and collect their outputs into a list,
    joined when all complete. The n-ary form of *; follow it with a reducer (e.g. + majority)
    to fold the list into one value. Named gather_all, not gather, so it never shadows
    asyncio.gather.
    """
    return _GatherAll(flows)


class _Nest(Flow[A, B]):
    def __init__(
        self,
        target: System | Flow[A, B],
        *,
        entry: str,
        out: str,
        until: Terminate | None,
    ) -> None:
        self._target = target
        self._entry = entry
        self._out = out
        self._until = until

    def _build(self, ctx: _Ctx, entry: str) -> tuple[list[Agent], str]:
        name = ctx.fresh("nest")
        inner_entry, inner_out = self._entry, self._out
        system = (
            self._target.system(entry=inner_entry, out=inner_out, llm=ctx.llm)
            if isinstance(self._target, Flow)
            else self._target
        )
        until = self._until or Goal(lambda v: v.exists(inner_out))

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

        return [as_agent(invoke, name=name, reads=entry)], name


def nest(
    target: System | Flow[A, B], *, entry: str, out: str, until: Terminate | None = None
) -> Flow[A, B]:
    """Run a whole sub-system as one typed arrow node: its own inner store, run to a goal,
    one fact out. The boundary is typed and composes; the interior stays opaque. This is
    how a goal-terminating blackboard surface enters the arrow world, and how a flow nests
    another flow as an isolated unit. Named nest, not embed, to avoid the embeddings reading.
    """
    return _Nest(target, entry=entry, out=out, until=until)
