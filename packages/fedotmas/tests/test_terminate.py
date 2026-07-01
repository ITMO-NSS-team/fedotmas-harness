"""Termination conditions: validation, the index axis, operator and function composition."""

import pytest
from fedotmas import Condition
from fedotmas.engine import (
    Budget,
    Fact,
    Goal,
    Quiescence,
    StepReport,
    Store,
    all_of,
    any_of,
)

EMPTY = Store().snapshot()


def report(index=0, step=None, fired=("x",)):
    return StepReport(step if step is not None else index, index, list(fired), [])


@pytest.mark.parametrize("bad", [0, -3])
def test_budget_rejects_non_positive(bad):
    with pytest.raises(ValueError, match="max_steps >= 1"):
        Budget(bad)


def test_budget_counts_the_index_axis():
    budget = Budget(3)
    assert not budget.done(EMPTY, report(index=1, step=99))
    assert budget.done(EMPTY, report(index=2, step=0))


def test_quiescence_is_an_empty_superstep():
    assert Quiescence().done(EMPTY, report(fired=()))
    assert not Quiescence().done(EMPTY, report())


def test_operator_composition():
    store = Store()
    term = Goal(lambda v: v.exists("done")) | Budget(2)
    assert not term.done(store.snapshot(), report(index=0))
    assert term.done(store.snapshot(), report(index=1))
    store.commit([Fact(tag="done", step=0)])
    assert term.done(store.snapshot(), report(index=0))


def test_any_of_lifts_a_bare_protocol_terminate():
    class Always:
        def done(self, view, report):
            return True

    assert any_of(Always(), Budget(5)).done(EMPTY, report())
    assert not all_of(Always(), Budget(5)).done(EMPTY, report())


def test_goal_accepts_a_condition_over_the_view():
    term = Goal(Condition(key="score", op="gte", value=3))
    store = Store()
    store.commit([Fact(tag="score", value=1, step=0)])
    assert not term.done(store.snapshot(), report())
    store.commit([Fact(tag="score", value=5, step=1)])
    assert term.done(store.snapshot(), report())


@pytest.mark.parametrize("compose", [all_of, any_of])
def test_composers_reject_empty(compose):
    with pytest.raises(ValueError, match="at least one"):
        compose()
