"""Menu cells build, run under a stub llm, and resolve uniquely from recipes."""

from itertools import product
from typing import Any

import pytest
from fedotmas.serialize import to_blueprint
from fedotmas_llm import Call
from fedotmas_meta import (
    MENU,
    Recipe,
    Review,
    cell_for,
    compile_recipe,
    menu_card,
    resolve,
)

FILLS = {
    "single": {"agent": "solve"},
    "chain": {"steps": {"extract": "extract", "solve": "solve"}},
    "debate": {
        "debaters": {"pro": "argue for", "con": "argue against"},
        "judge": "pick",
    },
    "eval_optimizer": {"generator": "draft", "critic": "review"},
    "orchestrator": {
        "planner": "plan",
        "workers": {"extract": "extract", "compute": "compute"},
        "synthesizer": "merge",
    },
    "blackboard": {
        "researcher": "facts",
        "skeptic": "check",
        "synthesizer": "conclude",
    },
    "orchestrator_blackboard": {
        "planner": "plan",
        "workers": {"extract": "extract", "compute": "compute"},
        "skeptic": "check",
        "synthesizer": "conclude",
    },
    "chain_critic": {
        "steps": {"extract": "extract", "solve": "solve"},
        "critic": "review",
    },
    "self_consistency": {"solver": "solve"},
}


class StubLLM:
    async def complete(self, call: Call, view: Any) -> Any:
        if call.returns is Review:
            return Review(approved=True, feedback="ok")
        return f"[{call.prompt}] {str(call.input)[:40]}"


@pytest.mark.parametrize("name", sorted(MENU))
async def test_every_cell_runs_under_a_stub(name: str):
    cell = MENU[name]
    flow = compile_recipe(cell.recipe, FILLS[name])
    run = await flow.run("what is 2 + 2?", bind={"llm": StubLLM()}, budget=30)
    assert run.ok, (run.reason, run.errors)
    assert isinstance(run.value, str) and run.value


@pytest.mark.parametrize("name", sorted(MENU))
def test_every_cell_projects_a_blueprint(name: str):
    cell = MENU[name]
    flow = cell.build(FILLS[name], cell.recipe)
    bp = to_blueprint(flow.system(entry="in", out="out", bind={"llm": StubLLM()}))
    assert bp.nodes


def test_recipes_resolve_to_their_cells():
    assert cell_for(Recipe()).name == "single"
    assert cell_for(Recipe(width=4)).name == "self_consistency"
    assert cell_for(Recipe(width=3, verify="judge")).name == "debate"
    assert cell_for(Recipe(iterate=2, verify="critic")).name == "eval_optimizer"
    assert (
        cell_for(Recipe(decompose="master", cooperate="shared")).name
        == "orchestrator_blackboard"
    )


def test_no_lattice_point_is_ambiguous():
    lattice = product(
        ("none", "pipeline", "master"),
        ("none", "shared"),
        (1, 2, 3),
        (0, 1, 2),
        ("none", "judge", "critic"),
    )
    for d, c, w, i, v in lattice:
        recipe = Recipe(decompose=d, cooperate=c, width=w, iterate=i, verify=v)
        try:
            cell_for(recipe)
        except LookupError as e:
            assert "matches" not in str(e), str(e)


def test_off_menu_recipe_names_the_menu():
    with pytest.raises(LookupError, match="no menu cell"):
        cell_for(Recipe(decompose="master", verify="judge"))


def test_cell_for_takes_a_caller_menu():
    menu = {"single": MENU["single"], "chain": MENU["chain"]}
    assert cell_for(Recipe(decompose="pipeline"), menu).name == "chain"
    with pytest.raises(LookupError):
        cell_for(Recipe(width=3), menu)


def test_menu_card_shows_coordinates_not_names():
    card = menu_card()
    assert len(card.splitlines()) == 9
    assert "single" not in card and "orchestrator" not in card


def test_near_canonical_recipes_resolve_by_fixed_axes():
    assert resolve(Recipe(verify="judge")).name == "debate"
    assert resolve(Recipe(iterate=0, verify="critic")).name == "eval_optimizer"
    assert resolve(Recipe(decompose="master", verify="judge")).name == "single"


def test_resolve_without_single_fallback_raises():
    menu = {"chain": MENU["chain"]}
    with pytest.raises(LookupError, match="no 'single' fallback"):
        resolve(Recipe(decompose="master", verify="judge"), menu)


class CountingLLM(StubLLM):
    def __init__(self, approve: bool = True) -> None:
        self.calls = 0
        self.approve = approve

    async def complete(self, call: Call, view: Any) -> Any:
        self.calls += 1
        if call.returns is Review:
            return Review(approved=self.approve, feedback="again")
        return await super().complete(call, view)


async def test_debate_width_sets_the_solver_count():
    for width, calls in ((2, 3), (4, 5)):
        llm = CountingLLM()
        flow = compile_recipe(Recipe(width=width, verify="judge"), FILLS["debate"])
        run = await flow.run("what is 2 + 2?", bind={"llm": llm}, budget=30)
        assert run.ok
        assert llm.calls == calls


async def test_iterate_caps_the_revision_rounds():
    for iterate, calls in ((1, 4), (3, 8)):
        llm = CountingLLM(approve=False)
        flow = compile_recipe(
            Recipe(iterate=iterate, verify="critic"), FILLS["eval_optimizer"]
        )
        run = await flow.run("what is 2 + 2?", bind={"llm": llm}, budget=60)
        assert run.ok, (run.reason, run.errors)
        assert llm.calls == calls
