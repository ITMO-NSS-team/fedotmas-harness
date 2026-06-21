from __future__ import annotations

from typing import Any

from pydantic import create_model

from fedotmas.atoms import action
from fedotmas.dsl._errors import Issue, ManifestError
from fedotmas.dsl._manifest import (
    AtomRef,
    Branch,
    Gather,
    Loop,
    Manifest,
    ManifestRef,
    Nest,
    NodeDef,
    Step,
    TypeRef,
)
from fedotmas.flow import Flow, branch, gather, nest

_TYPES: dict[str, type] = {
    "str": str,
    "int": int,
    "float": float,
    "bool": bool,
    "dict": dict,
}
_FIELDS: dict[str, type] = {"str": str, "int": int, "float": float, "bool": bool}
_LISTS: dict[str, type] = {
    "str": list[str],
    "int": list[int],
    "float": list[float],
    "bool": list[bool],
}


async def _skip(value: Any, view: Any) -> Any:
    return value


def _invalid() -> Flow[Any, Any]:
    return action(_skip, name="invalid")


def compile(
    manifest: Manifest,
    *,
    atoms: dict[str, Flow[Any, Any]] | None = None,
    types: dict[str, type] | None = None,
    providers: dict[str, Any] | None = None,
) -> Flow[Any, Any]:
    """Turn a validated manifest into one Flow, deterministically: same document, same
    graph. `atoms` fills ref: nodes, `types` names the takes/returns models, `providers` maps a
    node-kind to its builder. Prompt nodes (a bare string or a Prompted) need
    providers["agent"], supplied by the LLM extension as fedotmas_llm.agent. Run configuration
    (the llm via bind, budget, halt_on_error) stays at the call site."""
    if manifest.flow is None:
        raise ManifestError(
            [
                Issue(
                    path="flow",
                    message="the document has no flow to compile",
                    expected="a flow expression",
                )
            ]
        )
    compiler = _Compiler(manifest, atoms or {}, types or {}, providers or {})
    flow = compiler.run()
    if compiler.issues:
        raise ManifestError(compiler.issues)
    return flow


class _Compiler:
    def __init__(
        self,
        manifest: Manifest,
        atoms: dict[str, Flow[Any, Any]],
        types: dict[str, type],
        providers: dict[str, Any],
    ) -> None:
        self.manifest = manifest
        self.atoms = atoms
        self.types = types
        self.providers = providers
        self.issues: list[Issue] = []
        self.nodes: dict[str, Flow[Any, Any]] = {}
        self.spliced: dict[str, Flow[Any, Any]] = {}

    def run(self) -> Flow[Any, Any]:
        for name, d in self.manifest.nodes.items():
            self.nodes[name] = self.node(name, d)
        return self.expr(self.manifest.flow, "flow", ())

    def fail(self, path: str, message: str, expected: str | None = None) -> None:
        self.issues.append(Issue(path=path, message=message, expected=expected))

    def node(self, name: str, d: NodeDef) -> Flow[Any, Any]:
        path = f"nodes.{name}"
        if isinstance(d, str):
            return self._agent(name, path, prompt=d)
        if isinstance(d, AtomRef):
            flow = self.atoms.get(d.ref)
            if flow is None:
                self.fail(
                    f"{path}.ref",
                    f"unknown atom {d.ref!r}",
                    expected=f"one of {sorted(self.atoms)}"
                    if self.atoms
                    else "a registered atom",
                )
                return _invalid()
            return flow
        takes = self.typeof(d.takes, f"{path}.takes", f"{name}.takes")
        if d.labels is not None:
            return self._agent(
                name,
                path,
                prompt=d.prompt,
                input=d.input,
                takes=takes,
                labels=list(d.labels),
            )
        returns = self.typeof(d.returns, f"{path}.returns", f"{name}.returns")
        return self._agent(
            name, path, prompt=d.prompt, input=d.input, takes=takes, returns=returns
        )

    def _agent(self, name: str, path: str, **kw: Any) -> Flow[Any, Any]:
        builder = self.providers.get("agent")
        if builder is None:
            self.fail(
                path,
                "prompt nodes need an 'agent' provider",
                expected="compile(..., providers={'agent': fedotmas_llm.agent})",
            )
            return _invalid()
        return builder(name, **kw)

    def typeof(self, ref: TypeRef | None, path: str, hint: str) -> type:
        if ref is None:
            return str
        if isinstance(ref, str):
            t = _TYPES.get(ref) or self.types.get(ref)
            if t is None:
                self.fail(
                    path,
                    f"unknown type {ref!r}",
                    expected="str|int|float|bool|dict, a registered type name, or inline fields",
                )
                return str
            return t
        fields = {
            f: (_LISTS[k[0]] if isinstance(k, list) else _FIELDS[k], ...)
            for f, k in ref.items()
        }
        return create_model(hint, **fields)  # ty: ignore[no-matching-overload]

    def expr(self, e: Any, path: str, stack: tuple[str, ...]) -> Flow[Any, Any]:
        if isinstance(e, str):
            return self.ref(e, path, stack)
        if isinstance(e, list):
            flows = [self.expr(item, f"{path}.{i}", stack) for i, item in enumerate(e)]
            out = flows[0]
            for step in flows[1:]:
                out = out + step
            return out
        if isinstance(e, Gather):
            return gather(
                *(
                    self.expr(item, f"{path}.gather.{i}", stack)
                    for i, item in enumerate(e.gather)
                )
            )
        if isinstance(e, Branch):
            cases = {
                label: self.expr(case, f"{path}.cases.{label}", stack)
                for label, case in e.cases.items()
            }
            return branch(e.branch, cases)
        if isinstance(e, Loop):
            body = self.expr(e.loop, f"{path}.loop", stack)
            if e.budget is not None:
                return body.loop(e.until, budget=e.budget)
            return body.loop(e.until)
        if isinstance(e, Nest):
            if isinstance(e.nest, ManifestRef):
                self.fail(
                    f"{path}.nest",
                    "manifest-as-node is reserved, not implemented in v1",
                    expected="a flow expression",
                )
                return _invalid()
            inner = self.expr(e.nest, f"{path}.nest", stack)
            if e.budget is not None:
                return nest(inner, entry="in", out="out", budget=e.budget)
            return nest(inner, entry="in", out="out")
        assert isinstance(e, Step)
        inner = self.expr(e.step, f"{path}.step", stack)
        return inner.into(e.into) if e.into is not None else inner.merge()

    def ref(self, name: str, path: str, stack: tuple[str, ...]) -> Flow[Any, Any]:
        node = self.nodes.get(name)
        if node is not None:
            return node
        named = self.manifest.flows.get(name)
        if named is not None:
            if name in stack:
                self.fail(
                    path, f"circular flow reference: {' -> '.join((*stack, name))}"
                )
                return _invalid()
            if name not in self.spliced:
                self.spliced[name] = self.expr(named, f"flows.{name}", (*stack, name))
            return self.spliced[name]
        pool = sorted([*self.manifest.nodes, *self.manifest.flows])
        self.fail(
            path,
            f"unknown name {name!r}",
            expected=f"one of {pool}" if pool else "a node or flow name",
        )
        return _invalid()
