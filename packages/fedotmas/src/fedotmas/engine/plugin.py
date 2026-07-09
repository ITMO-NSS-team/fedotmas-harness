from __future__ import annotations

import difflib
import inspect
import warnings
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from fedotmas.engine.contract import Fact, Node, Result, View
    from fedotmas.engine.report import Run, StepReport
    from fedotmas.engine.system import System

PREFIXES = ("before", "after", "around", "on")


class PluginError(Exception):
    """A plugin is wired wrong: not a Plugin subclass, an unknown hook name, a sync or
    non-callable override, or a duplicate event registration. Raised when the dispatcher is
    built, before the run starts."""


class PluginWarning(Warning):
    """An observer hook raised; the run continues past it."""


@dataclass(frozen=True)
class Hook:
    """A hook point plugins attach to, named by `<prefix>_<name>` methods. Observers
    (`intercepts=False`: run, step, and events) return nothing, follow nested runs, and a
    raise is caught and warned. The interceptor hook (node) can rewrite the value, stays at
    the level the plugins were attached (see `PluginDispatcher.nested`), and a raise
    propagates as that node's error."""

    name: str
    prefixes: tuple[str, ...]
    intercepts: bool


HOOKS: dict[str, Hook] = {
    "run": Hook("run", ("before", "after"), intercepts=False),
    "step": Hook("step", ("after",), intercepts=False),
    "node": Hook("node", ("before", "after", "around"), intercepts=True),
}


def register_event(name: str) -> None:
    """Register an event hook: fired 0..N times through `PluginDispatcher.emit`, observed by
    an `on_<name>` plugin method. Extension packages call this at import."""
    if name in HOOKS:
        raise PluginError(f"hook {name!r} already registered")
    HOOKS[name] = Hook(name, ("on",), intercepts=False)


register_event("error")


class Plugin:
    """Base class for plugins; subclassing is required. Override the subset you need:
    observers (`before_run`, `after_step`, `after_run`, `on_error`) watch the run and return
    nothing; interceptors (`before_node`, `around_node`, `after_node`) rewrite a node's
    input, call, or result. Every hook method is `async def`; an unused parameter in an
    override is expected. A method whose name starts with a hook prefix but names no known
    hook fails at bind, so a typo cannot silently no-op."""

    async def before_run(
        self, system: System, view: View, scope: tuple[str, ...]
    ) -> None: ...

    async def after_run(self, run: Run) -> None: ...

    async def after_step(self, report: StepReport) -> None: ...

    async def before_node(
        self, node: Node, input: list[Fact], view: View
    ) -> list[Fact] | None: ...

    async def after_node(
        self, node: Node, result: Result, view: View
    ) -> Result | None: ...

    async def around_node(
        self,
        node: Node,
        input: list[Fact],
        view: View,
        call: Callable[[list[Fact], View], Awaitable[Result]],
    ) -> Result:
        return await call(input, view)

    async def on_error(self, node: Node, error: Fact, view: View) -> None: ...


def _suggest(prefix: str, suffix: str) -> str:
    near = difflib.get_close_matches(suffix, list(HOOKS), n=1)
    if near:
        return f"did you mean {f'{prefix}_{near[0]}'!r}?"
    return f"known hooks: {sorted(HOOKS)}"


def _check_names(cls: type) -> None:
    """A reserved-prefix method defined on a Plugin subclass must name a known hook and a
    supported phase. Only class-level callables are checked: data attributes and instance
    attributes never trip this."""
    for klass in cls.__mro__:
        if klass is Plugin:
            return
        for name, attr in vars(klass).items():
            if not callable(attr):
                continue
            prefix, sep, suffix = name.partition("_")
            if not sep or prefix not in PREFIXES:
                continue
            hook = HOOKS.get(suffix)
            if hook is None:
                raise PluginError(
                    f"{klass.__name__}.{name}: unknown hook {suffix!r}. "
                    f"{_suggest(prefix, suffix)}"
                )
            if prefix not in hook.prefixes:
                raise PluginError(
                    f"{klass.__name__}.{name}: hook {suffix!r} supports "
                    f"{hook.prefixes}, not {prefix!r}"
                )


def _hook_names() -> list[str]:
    return [f"{p}_{hook.name}" for hook in HOOKS.values() for p in hook.prefixes]


def _methods(plugin: Plugin) -> dict[str, Callable[..., Awaitable[Any]]]:
    """The plugin's active hook methods by name. Active means the resolved attribute — a
    class-level override or an instance attribute — differs from the Plugin base no-op.
    No reflection over the instance: only registered hook names are looked up."""
    if not isinstance(plugin, Plugin):
        raise PluginError(
            f"{type(plugin).__name__} is not a Plugin; plugins subclass fedotmas.Plugin"
        )
    _check_names(type(plugin))
    active: dict[str, Callable[..., Awaitable[Any]]] = {}
    for name in _hook_names():
        method: Any = getattr(plugin, name, None)
        base = getattr(Plugin, name, None)
        if method is None and base is None:
            continue  # an event this plugin does not observe
        if getattr(method, "__func__", method) is base:
            continue  # the inherited no-op
        if not callable(method):
            raise PluginError(
                f"{name!r} must be an `async def` method, got {type(method).__name__}"
            )
        if not inspect.iscoroutinefunction(getattr(method, "__func__", method)):
            raise PluginError(f"{name!r}: a hook method must be `async def`")
        active[name] = cast("Callable[..., Awaitable[Any]]", method)
    return active


NodeCall = Callable[[list["Fact"], "View"], Awaitable["Result"]]
_Layer = tuple[
    Callable[..., Awaitable[Any]] | None,
    Callable[..., Awaitable[Any]] | None,
    Callable[..., Awaitable[Any]] | None,
]


def _wrap(node: Node, layer: _Layer, inner: NodeCall) -> NodeCall:
    """One onion layer: before rewrites the input, around wraps the inner continuation, after
    rewrites the result. A `None` return from before or after keeps the current value."""
    before, around, after = layer

    async def call(input: list[Fact], view: View) -> Result:
        if before is not None:
            out = await before(node, input, view)
            if out is not None:
                input = out
        result = await (
            around(node, input, view, inner) if around else inner(input, view)
        )
        if after is not None:
            out = await after(node, result, view)
            if out is not None:
                result = out
        return result

    return call


class PluginDispatcher:
    """The bound form of a plugin list for one run: hook methods are validated and resolved
    once here, then fired — observers in list order, the interceptor onion folded around each
    node call with the first plugin outermost. An observer raise is caught and warned
    (`PluginWarning`); an interceptor raise propagates and becomes that node's error fact.
    `scope` is the nesting path stamped on reports, `()` at the root."""

    def __init__(
        self, plugins: Sequence[Plugin] = (), *, scope: tuple[str, ...] = ()
    ) -> None:
        table = [_methods(p) for p in plugins]
        self.scope = scope
        self._before_run = [t["before_run"] for t in table if "before_run" in t]
        self._after_run = [t["after_run"] for t in table if "after_run" in t]
        self._after_step = [t["after_step"] for t in table if "after_step" in t]
        self._events = {
            name: [t[f"on_{name}"] for t in table if f"on_{name}" in t]
            for name, hook in HOOKS.items()
            if hook.prefixes == ("on",)
        }
        self._layers: list[_Layer] = [
            (t.get("before_node"), t.get("around_node"), t.get("after_node"))
            for t in table
            if t.keys() & {"before_node", "around_node", "after_node"}
        ]

    @classmethod
    def of(cls, plugins: Sequence[Plugin] | PluginDispatcher) -> PluginDispatcher:
        """Normalize the public `plugins=` argument: a raw sequence binds here, an
        already-built dispatcher passes through unchanged."""
        return plugins if isinstance(plugins, PluginDispatcher) else cls(plugins)

    def nested(self, name: str) -> PluginDispatcher:
        """The dispatcher an inner run (a nest, a loop round) receives: observers and events
        follow the run inward under `scope + name`, the interceptor onion stays at the level
        the plugins were attached — Retry wraps the visible node once instead of multiplying
        through nesting. Shares the parent's resolved methods; nothing is re-validated."""
        child = PluginDispatcher(scope=(*self.scope, name))
        child._before_run = self._before_run
        child._after_run = self._after_run
        child._after_step = self._after_step
        child._events = self._events
        return child

    async def _observe(
        self, methods: Sequence[Callable[..., Awaitable[Any]]], *args: Any
    ) -> None:
        for m in methods:
            try:
                await m(*args)
            except Exception as exc:
                name = getattr(m, "__qualname__", repr(m))
                warnings.warn(f"{name} raised: {exc!r}", PluginWarning, stacklevel=2)

    async def before_run(self, system: System, view: View) -> None:
        await self._observe(self._before_run, system, view, self.scope)

    async def after_run(self, run: Run) -> None:
        await self._observe(self._after_run, run)

    async def after_step(self, report: StepReport) -> None:
        await self._observe(self._after_step, report)

    async def emit(self, event: str, *args: Any) -> None:
        """Fire an event hook's observers; unknown events are a silent no-op so an emit does
        not depend on which extensions are installed."""
        await self._observe(self._events.get(event, ()), *args)

    async def on_error(self, node: Node, error: Fact, view: View) -> None:
        await self.emit("error", node, error, view)

    async def invoke(self, node: Node, input: list[Fact], view: View) -> Result:
        """Run the node through the interceptor onion. A plugin raise here propagates, so the
        executor's `return_exceptions=True` turns it into that node's error fact."""
        call: NodeCall = node.invoke
        for layer in reversed(self._layers):
            call = _wrap(node, layer, call)
        return await call(input, view)


__all__ = [
    "HOOKS",
    "Hook",
    "Plugin",
    "PluginDispatcher",
    "PluginError",
    "PluginWarning",
    "register_event",
]
