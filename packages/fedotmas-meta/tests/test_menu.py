"""Menu cells build, run under a stub llm, and resolve uniquely from recipes."""

from itertools import product
from typing import Any

import pytest
from fedotmas.serialize import to_blueprint
from fedotmas_llm import Call
from fedotmas_meta import MENU, Recipe, Review, cell_for, compile_recipe

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
