from __future__ import annotations

import re
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from fedotmas import Flow
from fedotmas_llm import LLM, FunctionTool, MCPTool, Tool

from fedotmas_meta.presets import Preset, check_fill
from fedotmas_meta.presets._spec import AgentSpec, Bound, SystemSpec

# a tool string is an MCP server when it opens with a url scheme (http://, sse://, ...);
# anything else is a key into the local tools registry
_URL = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*://")


def _tool(name: str, registry: Mapping[str, Callable[..., Any]]) -> Tool:
    if _URL.match(name):
        return MCPTool(name)
    if name not in registry:
        raise KeyError(f"unknown tool {name!r}; not in the tools registry")
    return FunctionTool(name, registry[name])


def _bind(
    spec: AgentSpec,
    models: Mapping[str, LLM],
    tools: Mapping[str, Callable[..., Any]],
) -> Bound:
    llm: LLM | None = None
    if spec.model is not None:
        if spec.model not in models:
            raise KeyError(f"unknown model {spec.model!r}; not in the models registry")
        llm = models[spec.model]
    return Bound(spec.prompt, llm, tuple(_tool(t, tools) for t in spec.tools))


def _preset(name: str, presets: Sequence[Preset]) -> Preset:
    for p in presets:
        if p.name == name:
            return p
    raise KeyError(f"unknown preset {name!r}; one of {[p.name for p in presets]}")


def assemble(
    spec: SystemSpec,
    *,
    presets: Sequence[Preset],
    models: Mapping[str, LLM] | None = None,
    tools: Mapping[str, Callable[..., Any]] | None = None,
) -> Flow[Any, Any]:
    """Turn a SystemSpec into a runnable Flow: pick the named preset from the caller's catalog,
    resolve each AgentSpec's model and tool strings against the registries, then let the preset
    wire the bound agents. The preset is the fixed structure; the spec only fills its slots, so
    updating a surface never edits a spec, and the menu of presets is the caller's to choose."""
    models = models or {}
    tools = tools or {}
    preset = _preset(spec.preset, presets)
    check_fill(preset.name, preset.roles, spec.fill, preset.reserved)
    resolved: dict[str, Bound | dict[str, Bound]] = {}
    for role, value in spec.fill.items():
        if isinstance(value, dict):
            resolved[role] = {k: _bind(v, models, tools) for k, v in value.items()}
        else:
            resolved[role] = _bind(value, models, tools)
    return preset.build(resolved)
