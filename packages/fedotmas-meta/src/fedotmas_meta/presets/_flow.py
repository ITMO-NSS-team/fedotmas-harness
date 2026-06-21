from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from fedotmas import Flow, action, dsl
from fedotmas.engine import View
from fedotmas_llm import agent

from fedotmas_meta.presets._spec import Fill, RoleSpec, check_fill


@dataclass(frozen=True)
class FlowPreset:
    """A DataPreset whose body is a DSL manifest. `_doc` builds the document from the checked
    filling, `_atoms` supplies the code nodes it refs, `_reserved` are names the wiring owns
    that a role filling may not shadow."""

    name: str
    hint: str
    roles: tuple[RoleSpec, ...]
    _doc: Callable[[dict[str, Any]], dict[str, Any]]
    _atoms: dict[str, Flow[Any, Any]] = field(default_factory=dict)
    _reserved: frozenset[str] = frozenset()

    def manifest(self, roles: Fill) -> dsl.Manifest:
        fill = check_fill(self.name, self.roles, roles, self._reserved)
        return dsl.Manifest.model_validate(self._doc(fill))

    def build(self, roles: Fill) -> Flow[Any, Any]:
        return dsl.compile(
            self.manifest(roles), atoms=self._atoms, providers={"agent": agent}
        )


def _lift(**seed: Any) -> Flow[Any, Any]:
    async def lift(task: Any, view: View) -> dict[str, Any]:
        return {"task": task, **seed}

    return action(lift, name="lift")


async def _emit_draft(state: dict[str, Any], view: View) -> Any:
    return state["draft"]


async def _log_note(state: dict[str, Any], view: View) -> dict[str, Any]:
    return {**state, "notes": f"{state['notes']}\n- {state['note']}".strip()}


async def _keep(state: dict[str, Any], view: View) -> dict[str, Any]:
    return state


def _single(f: dict[str, Any]) -> dict[str, Any]:
    return {"version": 1, "nodes": {"agent": f["agent"]}, "flow": "agent"}


def _chain(f: dict[str, Any]) -> dict[str, Any]:
    return {"version": 1, "nodes": dict(f["steps"]), "flow": list(f["steps"])}


def _debate(f: dict[str, Any]) -> dict[str, Any]:
    return {
        "version": 1,
        "nodes": {"pro": f["pro"], "con": f["con"], "judge": f["judge"]},
        "flow": [{"gather": ["pro", "con"]}, "judge"],
    }


def _eval_optimizer(f: dict[str, Any]) -> dict[str, Any]:
    return {
        "version": 1,
        "nodes": {
            "lift": {"ref": "lift"},
            "generator": {
                "prompt": f["generator"],
                "takes": "dict",
                "input": "Task: {task}\n\nCurrent draft (empty if none):\n{draft}",
            },
            "critic": {
                "prompt": f["critic"],
                "takes": "dict",
                "input": "Task: {task}\n\nDraft:\n{draft}",
                "labels": ["approve", "revise"],
            },
            "emit": {"ref": "emit"},
        },
        "flow": [
            "lift",
            {
                "loop": [
                    {"step": "generator", "into": "draft"},
                    {"step": "critic", "into": "verdict"},
                ],
                "until": {"key": "verdict", "op": "eq", "value": "approve"},
            },
            "emit",
        ],
    }


def _router(f: dict[str, Any]) -> dict[str, Any]:
    handlers: dict[str, str] = f["handlers"]
    return {
        "version": 1,
        "nodes": {
            "lift": {"ref": "lift"},
            "dispatch": {
                "prompt": "Route the task to the specialist best suited to handle it.",
                "takes": "dict",
                "input": "{task}",
                "labels": list(handlers),
            },
            **{
                name: {"prompt": prompt, "takes": "dict", "input": "{task}"}
                for name, prompt in handlers.items()
            },
        },
        "flow": [
            "lift",
            {"step": "dispatch", "into": "route"},
            {"branch": "route", "cases": {name: name for name in handlers}},
        ],
    }


def _orchestrator(f: dict[str, Any]) -> dict[str, Any]:
    workers: dict[str, str] = f["workers"]
    see = "Task: {task}\n\nNotes so far:\n{notes}"
    return {
        "version": 1,
        "nodes": {
            "lift": {"ref": "lift"},
            "plan": {
                "prompt": (
                    "You coordinate specialists on a task. Pick who works next,"
                    " or 'done' when the notes already cover the task."
                ),
                "takes": "dict",
                "input": see,
                "labels": [*workers, "done"],
            },
            **{
                name: {"prompt": prompt, "takes": "dict", "input": see}
                for name, prompt in workers.items()
            },
            "log": {"ref": "log"},
            "keep": {"ref": "keep"},
            "synthesize": {"prompt": f["synthesizer"], "takes": "dict", "input": see},
        },
        "flow": [
            "lift",
            {
                "loop": [
                    {"step": "plan", "into": "next"},
                    {
                        "branch": "next",
                        "cases": {
                            **{
                                name: [{"step": name, "into": "note"}, "log"]
                                for name in workers
                            },
                            "done": "keep",
                        },
                    },
                ],
                "until": {"key": "next", "op": "eq", "value": "done"},
            },
            "synthesize",
        ],
    }


SINGLE = FlowPreset(
    name="single",
    hint="one agent answers directly; the task is small and self-contained",
    roles=(RoleSpec("agent", "the one agent that does the whole task"),),
    _doc=_single,
)

CHAIN = FlowPreset(
    name="chain",
    hint="fixed pipeline of specialized steps, each consuming the previous output",
    roles=(
        RoleSpec(
            "steps",
            "ordered name -> prompt steps; each consumes the previous output",
            many=True,
        ),
    ),
    _doc=_chain,
)

DEBATE = FlowPreset(
    name="debate",
    hint="parallel agents argue or vote; contested judgement or error-prone reasoning",
    roles=(
        RoleSpec("pro", "argues for"),
        RoleSpec("con", "argues against"),
        RoleSpec("judge", "weighs both sides and returns the verdict"),
    ),
    _doc=_debate,
)

EVAL_OPTIMIZER = FlowPreset(
    name="eval_optimizer",
    hint="generator improves a draft in a loop until a critic approves",
    roles=(
        RoleSpec("generator", "writes and rewrites the draft"),
        RoleSpec("critic", "judges the draft: approve, or demand another round"),
    ),
    _doc=_eval_optimizer,
    _atoms={"lift": _lift(draft=""), "emit": action(_emit_draft, name="emit")},
)

ROUTER = FlowPreset(
    name="router",
    hint="incoming items are dispatched to one of several specialist handlers",
    roles=(
        RoleSpec(
            "handlers",
            "specialist handlers, name -> prompt; names become routing labels",
            many=True,
        ),
    ),
    _doc=_router,
    _atoms={"lift": _lift()},
    _reserved=frozenset({"lift", "dispatch"}),
)

ORCHESTRATOR = FlowPreset(
    name="orchestrator",
    hint="a coordinator decides at runtime which specialist works next",
    roles=(
        RoleSpec(
            "workers",
            "specialists the coordinator can call, name -> prompt",
            many=True,
        ),
        RoleSpec("synthesizer", "folds the accumulated notes into the final answer"),
    ),
    _doc=_orchestrator,
    _atoms={
        "lift": _lift(notes=""),
        "log": action(_log_note, name="log"),
        "keep": action(_keep, name="keep"),
    },
    _reserved=frozenset({"lift", "plan", "log", "keep", "synthesize", "done"}),
)
