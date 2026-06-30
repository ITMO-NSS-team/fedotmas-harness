from __future__ import annotations

from collections.abc import AsyncIterator, Callable, Mapping
from typing import TYPE_CHECKING, Any, Generic, TypeVar

from fedotmas._condition import Predicate, _pick, state_predicate
from fedotmas._inject import bind_pred
from fedotmas._outcome import Outcome
from fedotmas.engine.contract import Fact, Kind, Node, View
from fedotmas.engine.executor import ReactiveExecutor
from fedotmas.engine.report import StepReport
from fedotmas.engine.store import Store
from fedotmas.engine.system import System
from fedotmas.engine.terminate import Budget, Goal, Terminate, any_of
from fedotmas.flow._nodes import (
    Ctx,
    _alias_node,
    _collect_node,
    _into_node,
    _loop_finish_node,
    _loop_iterate_node,
    _merge_node,
    _nest_node,
    _route_node,
)

if TYPE_CHECKING:
    from fedotmas.blackboard import Board
    from fedotmas.engine.policy import Policy

A = TypeVar("A")
B = TypeVar("B")
C = TypeVar("C")


class Flow(Generic[A, B]):
    """A typed dataflow fragment from input A to output B. Make atoms with action (a code
    body), or an extension node-kind such as fedotmas-llm's agent, then compose: + is
    sequence, gather runs branches in parallel, branch routes by label, .loop iterates, nest
    wraps a whole sub-system as one node. `.system(entry, out)`
    compiles the fragment to an engine System; `.run(value)` compiles and executes it in one
    call. The type parameters check each stitch: a + b only type-checks when b accepts what a
    produces.
    """

    def _build(self, ctx: Ctx, entry: str) -> tuple[list[Node], str]:
        raise NotImplementedError

    def system(
        self, *, entry: str, out: str, bind: Mapping[str, Any] | None = None
    ) -> System:
        """Compile to a runnable System. `bind` is the run-scoped binding map threaded to every
        node's builder (e.g. a default backend under "llm"); a node that needs a binding nobody
        supplied fails here, not mid-run."""
        ctx = Ctx(bindings=bind or {})
        nodes, last = self._build(ctx, entry)
        if last != out:
            nodes = [*nodes, _alias_node(last, out)]
        return System(nodes)

    def _prepare(
        self, bind: Mapping[str, Any] | None, budget: int | None
    ) -> tuple[System, Terminate]:
        system = self.system(entry="in", out="out", bind=bind)
        terminate: Terminate = Goal(lambda v: v.exists("out"))
        if budget is not None:
            terminate = terminate | Budget(budget)
        return system, terminate

    async def run(
        self,
        value: A,
        *,
        bind: Mapping[str, Any] | None = None,
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
        system, terminate = self._prepare(bind, budget)
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
        bind: Mapping[str, Any] | None = None,
        budget: int | None = 100,
        policy: Policy | None = None,
        halt_on_error: bool = True,
    ) -> AsyncIterator[StepReport]:
        """The streaming form of .run: yields each StepReport as the run unfolds."""
        system, terminate = self._prepare(bind, budget)
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

    def into(self: Flow[dict, Any], key: str) -> Flow[dict, dict]:
        """Thread a dict state past this flow: run it on the state, put its output under
        `key`, pass the other keys through unchanged. State-threading is composition, not a
        call parameter, so it works on any flow (an agent, an action, a nested system), and
        it is what lets stateless atoms fill loops, swarms, and chats."""
        return _Into(self, key)

    def merge(self: Flow[dict, Any]) -> Flow[dict, dict]:
        """Thread a dict state past this flow: fold the fields of its structured output into
        the state (a BaseModel output is dumped first). The output decides which keys change,
        which is what lets a handoff target ride inside the reply."""
        return _Merge(self)

    def loop(
        self: Flow[A, A],
        until: Callable[[A], bool] | Callable[[A, View], bool] | Predicate | str,
        *,
        budget: int | None = 100,
    ) -> Flow[A, A]:
        """Iterate the flow, feeding each round's output in as the next round's input, until
        `until` clears. `until` is a callable over the state (optionally the state and the
        view), a Condition or its `&`/`|`/`~` composition, or a state key (stop when state[key]
        is truthy). Each round runs the body in its own inner store as one outer superstep, so
        rounds are capped by the outer budget but a round itself is not; `budget` caps the
        supersteps inside one round (default 100, None lifts it).

        Example:
            revise.loop(until="approved")  # stop when state["approved"] is truthy
            revise.loop(until=lambda s: s["score"] >= 0.9)
        """
        fn, pred = state_predicate(until)
        return _Loop(self, fn, pred, budget)


class _Seq(Flow[Any, Any]):
    def __init__(self, left: Flow[Any, Any], right: Flow[Any, Any]) -> None:
        self._left = left
        self._right = right

    def _build(self, ctx: Ctx, entry: str) -> tuple[list[Node], str]:
        la, lout = self._left._build(ctx, entry)
        ra, rout = self._right._build(ctx, lout)
        return [*la, *ra], rout


class _Into(Flow[dict, dict]):
    def __init__(self, inner: Flow[Any, Any], key: str) -> None:
        self._inner = inner
        self._key = key

    def _build(self, ctx: Ctx, entry: str) -> tuple[list[Node], str]:
        nodes, reply = self._inner._build(ctx, entry)
        out = ctx.fresh("into")
        return [*nodes, _into_node(out, entry, reply, self._key)], out


class _Merge(Flow[dict, dict]):
    def __init__(self, inner: Flow[Any, Any]) -> None:
        self._inner = inner

    def _build(self, ctx: Ctx, entry: str) -> tuple[list[Node], str]:
        nodes, reply = self._inner._build(ctx, entry)
        out = ctx.fresh("merge")
        return [*nodes, _merge_node(out, entry, reply)], out


class _Loop(Flow[Any, Any]):
    def __init__(
        self,
        body: Flow[Any, Any],
        until: Callable[[Any, View], bool],
        pred: Predicate | None,
        budget: int | None,
    ) -> None:
        self._body = body
        self._until = until
        self._pred = pred
        self._budget = budget

    def _build(self, ctx: Ctx, entry: str) -> tuple[list[Node], str]:
        name = ctx.fresh("loop")
        state = f"{name}:s"
        body_in, body_out = f"{name}:in", f"{name}:out"
        body = self._body.system(entry=body_in, out=body_out, bind=ctx.bindings)
        round_term: Terminate = Goal(lambda v: v.exists(body_out))
        if self._budget is not None:
            round_term = any_of(round_term, Budget(self._budget))
        nodes = [
            _loop_iterate_node(
                name,
                body,
                body_in,
                body_out,
                entry,
                state,
                self._until,
                round_term,
                self._pred,
                self._budget,
            ),
            _loop_finish_node(name, state, name, self._until, self._pred),
        ]
        return nodes, name


class _Branch(Flow[Any, Any]):
    def __init__(
        self,
        select: Flow[Any, Any] | Callable[[Any, View], str],
        cases: dict[str, Flow[Any, Any]],
        select_spec: dict[str, Any],
    ) -> None:
        self._select = select
        self._cases = cases
        self._select_spec = select_spec

    def _build(self, ctx: Ctx, entry: str) -> tuple[list[Node], str]:
        name = ctx.fresh("branch")
        out = name
        ins = {k: f"{name}:in:{k}" for k in self._cases}
        select = self._select
        nodes: list[Node] = []

        label_tag = ""
        classify: Callable[[Any, View], str] | None = None
        if isinstance(select, Flow):
            sel_nodes, label_tag = select._build(ctx, entry)
            nodes.extend(sel_nodes)
            route_reads = label_tag
        else:
            classify = select
            route_reads = entry

        nodes.append(
            _route_node(
                name,
                route_reads,
                entry,
                classify,
                label_tag,
                ins,
                self._select_spec,
                list(self._cases),
            )
        )
        for k, case in self._cases.items():
            case_nodes, case_out = case._build(ctx, ins[k])
            nodes.extend(case_nodes)
            nodes.append(
                _alias_node(
                    case_out, out, name=f"{name}:join:{k}", kind=Kind.BRANCH_JOIN
                )
            )
        return nodes, out


def branch(
    select: Flow[A, str] | Callable[[A], str] | Callable[[A, View], str] | str,
    cases: dict[str, Flow[A, B]],
) -> Flow[A, B]:
    """Route the input to exactly one case by a label, then merge back to one output. `select`
    is a python callable A -> label (optionally (A, View) -> label), a state key (route by
    state[key], the declarative form), or a label-producing flow (an agent with labels=, when
    the route is the model's choice; an extra router step). All cases share input and output
    types, so the whole branch stays one typed arrow Flow[A, B].

    Example:
        kind = agent("kind", prompt="Classify the issue.", labels=["bug", "feature"])
        branch(kind, {"bug": triage, "feature": plan})
    """
    if isinstance(select, str):
        key = select
        spec: dict[str, Any] = {"by": "state", "key": key}
        return _Branch(lambda state, view: _pick(state, key), cases, spec)
    if not isinstance(select, Flow):
        return _Branch(bind_pred(select), cases, {"by": "callable"})
    return _Branch(select, cases, {"by": "flow"})


class _Gather(Flow[Any, Any]):
    def __init__(self, flows: tuple[Flow[Any, Any], ...]) -> None:
        self._flows = flows

    def _build(self, ctx: Ctx, entry: str) -> tuple[list[Node], str]:
        out = ctx.fresh("gather")
        nodes: list[Node] = []
        srcs: list[str] = []
        for flow in self._flows:
            built, fout = flow._build(ctx, entry)
            nodes.extend(built)
            srcs.append(fout)
        return [*nodes, _collect_node(out, srcs, out)], out


def gather(*flows: Flow[A, B]) -> Flow[A, list[B]]:
    """Run several flows on the same input in parallel and collect their outputs into a list,
    joined when all complete. The n-ary form of *; follow it with a reducer (e.g. + majority)
    to fold the list into one value. Matches the dsl `gather` form.

    Example:
        gather(solver_a, solver_b, solver_c) + majority  # self-consistency vote
    """
    if not flows:
        raise ValueError("gather needs at least one flow")
    return _Gather(flows)


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

    def _build(self, ctx: Ctx, entry: str) -> tuple[list[Node], str]:
        name = ctx.fresh("nest")
        inner_entry, inner_out = self._entry, self._out
        if isinstance(self._target, Flow):
            system = self._target.system(
                entry=inner_entry, out=inner_out, bind=ctx.bindings
            )
        elif isinstance(self._target, System):
            system = self._target
        else:  # a Board: thread the flow's run-scoped bindings as its rules' fallback
            system = self._target.compile(ctx.bindings)
        until = self._until or Goal(lambda v: v.exists(inner_out))
        if self._budget is not None:
            until = any_of(until, Budget(self._budget))
        nest = _nest_node(
            name, system, entry, inner_entry, inner_out, until, self._budget
        )
        return [nest], name


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
    flow's run-scoped bindings as its fallback; a System is already compiled, so they do not
    reach inside it. The inner run is the outer node's single superstep, so the
    outer budget cannot interrupt it; `budget` caps the inner supersteps instead (the default
    100 is a runaway guard, None lifts it). The inner run always halts on its first error and
    the failure surfaces as this node's error fact; the outer halt_on_error then decides
    whether the rest of the system continues. Named nest, not embed, to avoid the embeddings
    reading.

    Example:
        research = nest(board, entry="topic", out="report", until=Goal("report"))
        pipeline = plan + research + write
    """
    return _Nest(target, entry=entry, out=out, until=until, budget=budget)
