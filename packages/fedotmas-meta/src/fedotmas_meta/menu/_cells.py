from __future__ import annotations

import json
from collections import Counter
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from functools import reduce
from operator import add
from typing import Any

from fedotmas import Condition, Flow, action, blackboard, gather, nest
from fedotmas_llm import PromptRule, agent
from pydantic import BaseModel

from fedotmas_meta.menu._recipe import AXES, Recipe

Fill = Mapping[str, Any]


class Review(BaseModel):
    approved: bool
    feedback: str


@action
async def to_state(task: str) -> dict:
    return {"task": task, "draft": "", "feedback": "", "round": 0}


@action
async def bump(state: dict) -> dict:
    return {**state, "round": state["round"] + 1}


@action
async def take_draft(state: dict) -> str:
    return state["draft"]


@action
async def majority(answers: list[str]) -> str:
    return Counter(a.strip() for a in answers).most_common(1)[0][0]


def _seq(prompts: Mapping[str, str]) -> Flow[Any, Any]:
    return reduce(add, [agent(n, prompt=p) for n, p in prompts.items()])


def _revise_loop(
    drafting: Flow[Any, Any], critic_prompt: str, rounds: int
) -> Flow[Any, Any]:
    critic = agent(
        "critic",
        prompt=critic_prompt,
        input="Task: {task}\nDraft: {draft}",
        takes=dict,
        returns=Review,
    )
    done = Condition(key="approved") | Condition(key="round", op="gte", value=rounds)
    body = drafting.into("draft") + critic.merge() + bump
    return to_state + body.loop(until=done) + take_draft


def _single(fill: Fill, r: Recipe) -> Flow[Any, Any]:
    return agent("agent", prompt=fill["agent"])


def _chain(fill: Fill, r: Recipe) -> Flow[Any, Any]:
    return _seq(fill["steps"])


def _debate(fill: Fill, r: Recipe) -> Flow[Any, Any]:
    pairs = list(fill["debaters"].items())
    seats = [pairs[i % len(pairs)] for i in range(max(r.width, 2))]
    solvers = [
        agent(n if i < len(pairs) else f"{n}_{i}", prompt=p)
        for i, (n, p) in enumerate(seats)
    ]
    judge = agent("judge", prompt=fill["judge"], takes=list, returns=str)
    return gather(*solvers) + judge


def _self_consistency(fill: Fill, r: Recipe) -> Flow[Any, Any]:
    solvers = [agent(f"solver_{i}", prompt=fill["solver"]) for i in range(r.width)]
    return gather(*solvers) + majority


def _eval_optimizer(fill: Fill, r: Recipe) -> Flow[Any, Any]:
    generator = agent(
        "generator",
        prompt=fill["generator"],
        input="Task: {task}\nPrevious draft: {draft}\nFeedback: {feedback}",
        takes=dict,
        returns=str,
    )
    return _revise_loop(generator, fill["critic"], r.iterate + 1)


def _chain_critic(fill: Fill, r: Recipe) -> Flow[Any, Any]:
    names = list(fill["steps"])
    head = agent(
        names[0],
        prompt=fill["steps"][names[0]],
        input="Task: {task}\nFeedback from last round: {feedback}",
        takes=dict,
        returns=str,
    )
    rest = [agent(n, prompt=fill["steps"][n]) for n in names[1:]]
    return _revise_loop(reduce(add, [head, *rest]), fill["critic"], r.iterate + 1)


def _orchestrator(fill: Fill, r: Recipe) -> Flow[Any, Any]:
    plan = agent("planner", prompt=fill["planner"])
    workers = gather(*[agent(n, prompt=p) for n, p in fill["workers"].items()])
    synthesizer = agent(
        "synthesizer", prompt=fill["synthesizer"], takes=list, returns=str
    )
    return plan + workers + synthesizer


def _blackboard(fill: Fill, r: Recipe) -> Flow[Any, Any]:
    board = blackboard(
        PromptRule(
            "researcher", prompt=fill["researcher"], reads="task", writes="facts"
        ),
        PromptRule(
            "skeptic",
            prompt=fill["skeptic"],
            reads="facts",
            writes="review",
            when=["facts", "!review"],
        ),
        PromptRule(
            "synthesizer",
            prompt=fill["synthesizer"],
            input="Task: {task}\nFacts: {facts}\nReview: {review}",
            reads="facts",
            writes="answer",
            when=["facts", "review", "!answer"],
        ),
    )
    return nest(board, entry="task", out="answer")


def _orchestrator_blackboard(fill: Fill, r: Recipe) -> Flow[Any, Any]:
    notes = [f"note_{n}" for n in fill["workers"]]
    lines = "\n".join("{" + t + "}" for t in notes)
    rules = [
        PromptRule(n, prompt=p, reads="plan", writes=f"note_{n}")
        for n, p in fill["workers"].items()
    ]
    rules.append(
        PromptRule(
            "skeptic",
            prompt=fill["skeptic"],
            input=f"Plan: {{plan}}\n{lines}",
            reads="plan",
            writes="review",
            when=[*notes, "!review"],
        )
    )
    rules.append(
        PromptRule(
            "synthesizer",
            prompt=fill["synthesizer"],
            input=f"Plan: {{plan}}\n{lines}\nReview: {{review}}",
            reads="review",
            writes="answer",
            when=[*notes, "review", "!answer"],
        )
    )
    plan = agent("planner", prompt=fill["planner"])
    return plan + nest(blackboard(*rules), entry="plan", out="answer")


@dataclass(frozen=True)
class Cell:
    """One menu entry: a canonical Recipe point, free axes (knobs), fill roles, a builder."""

    name: str
    hint: str
    recipe: Recipe
    build: Callable[[Fill, Recipe], Flow[Any, Any]]
    knobs: frozenset[str] = frozenset()
    roles: tuple[str, ...] = ()
    many: frozenset[str] = frozenset()


MENU: dict[str, Cell] = {
    c.name: c
    for c in [
        Cell(
            "single",
            "One agent answers directly; no coordination overhead.",
            Recipe(),
            _single,
            roles=("agent",),
        ),
        Cell(
            "chain",
            "Sequential decomposition: fixed steps, each transforms the task once.",
            Recipe(decompose="pipeline"),
            _chain,
            roles=("steps",),
            many=frozenset({"steps"}),
        ),
        Cell(
            "debate",
            "Independent parallel solutions; a judge picks one.",
            Recipe(width=2, verify="judge"),
            _debate,
            knobs=frozenset({"width"}),
            roles=("debaters", "judge"),
            many=frozenset({"debaters"}),
        ),
        Cell(
            "eval_optimizer",
            "Draft-review loop: a critic gates revisions until approved.",
            Recipe(iterate=1, verify="critic"),
            _eval_optimizer,
            knobs=frozenset({"iterate"}),
            roles=("generator", "critic"),
        ),
        Cell(
            "orchestrator",
            "A planner decomposes; specialist workers run in parallel; a synthesizer merges.",
            Recipe(decompose="master"),
            _orchestrator,
            roles=("planner", "workers", "synthesizer"),
            many=frozenset({"workers"}),
        ),
        Cell(
            "blackboard",
            "Autonomous specialists cooperate through a shared store.",
            Recipe(cooperate="shared"),
            _blackboard,
            roles=("researcher", "skeptic", "synthesizer"),
        ),
        Cell(
            "orchestrator_blackboard",
            "Master decomposition over a shared store: a plan, cooperative workers, a check.",
            Recipe(decompose="master", cooperate="shared"),
            _orchestrator_blackboard,
            roles=("planner", "workers", "skeptic", "synthesizer"),
            many=frozenset({"workers"}),
        ),
        Cell(
            "chain_critic",
            "A step pipeline wrapped in a critic loop.",
            Recipe(decompose="pipeline", iterate=1, verify="critic"),
            _chain_critic,
            knobs=frozenset({"iterate"}),
            roles=("steps", "critic"),
            many=frozenset({"steps"}),
        ),
        Cell(
            "self_consistency",
            "Independent samples of one solver; the majority answer wins.",
            Recipe(width=3),
            _self_consistency,
            knobs=frozenset({"width"}),
            roles=("solver",),
        ),
    ]
}

_DEFAULTS = {a: Recipe.model_fields[a].default for a in AXES}


def _matches(recipe: Recipe, cell: Cell) -> bool:
    for a in AXES:
        v = getattr(recipe, a)
        if a in cell.knobs:
            if v == _DEFAULTS[a]:
                return False
        elif v != getattr(cell.recipe, a):
            return False
    return True


def cell_for(recipe: Recipe, menu: Mapping[str, Cell] = MENU) -> Cell:
    """The unique menu cell whose fixed axes match the recipe; knob axes stay free."""
    hits = [c for c in menu.values() if _matches(recipe, c)]
    if len(hits) == 1:
        return hits[0]
    coords = recipe.model_dump()
    if hits:
        raise LookupError(f"recipe {coords} matches {[c.name for c in hits]}")
    raise LookupError(f"no menu cell for recipe {coords}; menu: {sorted(menu)}")


def compile_recipe(
    recipe: Recipe, fill: Fill, menu: Mapping[str, Cell] = MENU
) -> Flow[Any, Any]:
    """Build the runnable Flow for a recipe: menu lookup plus knob substitution."""
    return cell_for(recipe, menu).build(fill, recipe)


def _matches_fixed(recipe: Recipe, cell: Cell) -> bool:
    return all(
        getattr(recipe, a) == getattr(cell.recipe, a)
        for a in AXES
        if a not in cell.knobs
    )


def resolve(recipe: Recipe, menu: Mapping[str, Cell] = MENU) -> Cell:
    """The menu cell for a recipe: exact match, else the unique cell whose fixed axes
    match (knobs left at default read as unspecified), else single."""
    try:
        return cell_for(recipe, menu)
    except LookupError:
        hits = [c for c in menu.values() if _matches_fixed(recipe, c)]
        if len(hits) == 1:
            return hits[0]
        if "single" in menu:
            return menu["single"]
        raise LookupError(
            f"recipe {recipe.model_dump()} is off-menu and the menu has no 'single' "
            f"fallback; menu: {sorted(menu)}"
        ) from None


def menu_card(menu: Mapping[str, Cell] = MENU) -> str:
    """The menu as selector input: one line per cell, coordinates and hint, no names."""
    return "\n".join(
        f"- {json.dumps(c.recipe.model_dump())}  {c.hint}" for c in menu.values()
    )
