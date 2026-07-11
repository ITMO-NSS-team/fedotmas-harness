"""Termination leaves: validation, the index axis, the Goal shorthand forms."""

import pytest
from fedotmas import Condition
from fedotmas.engine import Budget, Fact, Goal, StepReport, Store

EMPTY = Store().snapshot()


def report(index=0, step=None, fired=("x",)):
    return StepReport(
        step if step is not None else index, index, list(fired), [], EMPTY
    )


@pytest.mark.parametrize("bad", [0, -3])
def test_budget_rejects_non_positive(bad):
    with pytest.raises(ValueError, match="max_steps >= 1"):
        Budget(bad)


def test_budget_counts_the_index_axis():
    budget = Budget(3)
    assert not budget.done(EMPTY, report(index=1, step=99))
    assert budget.done(EMPTY, report(index=2, step=0))


def test_goal_tag_string_means_the_fact_exists():
    term = Goal("done")
    store = Store()
    assert not term.done(store.snapshot(), report())
    store.commit([Fact(tag="done", step=0)])
    assert term.done(store.snapshot(), report())


def test_goal_accepts_a_condition_over_the_view():
    term = Goal(Condition(key="score", op="gte", value=3))
    store = Store()
    store.commit([Fact(tag="score", value=1, step=0)])
    assert not term.done(store.snapshot(), report())
    store.commit([Fact(tag="score", value=5, step=1)])
    assert term.done(store.snapshot(), report())
