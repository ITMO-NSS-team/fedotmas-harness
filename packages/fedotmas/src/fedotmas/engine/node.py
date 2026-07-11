from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from typing import Any

from fedotmas.engine.contract import Card, Fact, Kind, Node, Result, View, patterns
from fedotmas.engine.executor import ReactiveExecutor
from fedotmas.engine.outcome import Outcome, RunError
from fedotmas.engine.plugin import PluginDispatcher
from fedotmas.engine.report import Run
from fedotmas.engine.store import Store
from fedotmas.engine.system import System
from fedotmas.engine.terminate import Budget, Goal, Terminate

Invoke = Callable[[Any, View], Awaitable[Result]]
Trigger = Callable[[View], bool]


class _FnNode:
    def __init__(
        self,
        fn: Invoke,
        name: str,
        reads: str,
        trigger: Trigger,
        meta: dict[str, Any],
        kind: str,
        writes: list[str],
        params: dict[str, Any],
        system: Any,
    ) -> None:
        self.name = name
        self.reads = reads
        self._fn = fn
        self._trigger = trigger
        self._meta = meta
        self._kind = kind
        self._writes = writes
        self._params = params
        self._system = system

    def trigger(self, view: View) -> bool:
        return self._trigger(view)

    async def invoke(self, input: Any, view: View) -> Result:
        return await self._fn(input, view)

    def describe(self) -> Card:
        return Card(
            name=self.name,
            description=self._fn.__doc__ or "",
            meta=self._meta,
            kind=self._kind,
            reads=patterns(self.reads),
            writes=self._writes,
            params=self._params,
            system=self._system,
        )


def as_node(
    fn: Invoke,
    *,
    name: str,
    reads: str = "",
    trigger: Trigger | None = None,
    meta: dict[str, Any] | None = None,
    kind: str = Kind.ACTION,
    writes: list[str] | None = None,
    params: dict[str, Any] | None = None,
    system: Any = None,
) -> Node:
    """Wrap an async (input, view) -> Result function as a Node. `reads` holds one or more
    whitespace-separated fact patterns: it is the input the executor matches for the node and
    the node's re-fire identity (see Node). The default trigger is "every reads pattern has a
    match"; with empty reads it is "never", so a node without reads needs an explicit
    `trigger` to fire at all (and then fires at most once per run).

    `kind`, `writes`, `params`, `system` are the node's declarative self-portrait for its Card
    and never touch execution; `writes` defaults to the node's own name, so only the kinds that
    write elsewhere (alias, rule, branch routing, loop) pass it explicitly. `system` is a live
    sub-system a walker recurses into (nest, loop).
    """
    if trigger is not None:
        trig = trigger
    elif reads:
        pats = patterns(reads)
        trig = lambda view: all(view.exists(p) for p in pats)  # noqa: E731
    else:
        trig = lambda view: False  # noqa: E731
    return _FnNode(
        fn,
        name,
        reads,
        trig,
        meta or {},
        kind,
        [name] if writes is None else writes,
        params or {},
        system,
    )


def system_step(
    system: System,
    *,
    entry: str,
    out: str,
    budget: int | None = 100,
    terminate: Sequence[Terminate] = (),
    plugins: PluginDispatcher | None = None,
    label: str = "nest",
) -> Callable[[Any], Awaitable[Any]]:
    """Compile a whole System into one async step — the recursion primitive both composition
    surfaces build on (a flow's nest node, a board's nest rule). Each call seeds a fresh inner
    store with the value under `entry`, runs until `out` exists (`terminate` replaces that
    default; `budget` caps the inner supersteps, None lifts it) and returns the value of
    `out`. A broken inner run raises RunError through inner_guard, with `label` naming this
    boundary in the message."""
    dispatcher = plugins or PluginDispatcher()
    term: list[Terminate] = list(terminate) or [Goal(out)]
    if budget is not None:
        term.append(Budget(budget))

    async def step(value: Any) -> Any:
        run = await ReactiveExecutor().run(
            system,
            Store(),
            seed=[Fact(tag=entry, value=value)],
            terminate=term,
            plugins=dispatcher,
        )
        inner_guard(run, out, label)
        return run.view.value(out)

    return step


def inner_guard(run: Run, out: str, what: str) -> None:
    """Surface an inner run's failure as the wrapping node's failure: RunError carries the
    inner error facts across the boundary, so the outer executor records them as that node's
    meta["causes"] tree instead of a flattened string. Only a strict inner system ends with
    reason "error"; a lenient one (halt_on_error=False) that still produced `out` passes,
    its recorded errors noise by its own declaration."""
    inner = Outcome(run, out)
    if run.reason == "error":
        msgs = "; ".join(f"{e.producer}: {e.value}" for e in inner.errors)
        raise RunError(
            f"{what}: inner system failed ({msgs})", errors=inner.errors, reason="error"
        )
    if not run.view.exists(out):
        raise RunError(
            f"{what}: inner system stopped ({run.reason}) before producing {out!r}",
            errors=inner.errors,
            reason=inner.reason,
        )
