"""Fact identity and the Store: keys, the logical clock, snapshot isolation, patterns."""

from fedotmas.engine import Fact, Store


def test_producer_is_part_of_the_key():
    a = Fact(tag="t", step=0, producer="x")
    b = Fact(tag="t", step=0, producer="y")
    assert a.key == ("t", 0, "x")
    assert a.key != b.key


def test_clock_is_one_past_the_highest_committed_step():
    store = Store()
    assert store.next_step() == 0
    store.commit([Fact(tag="a", step=0)])
    assert store.next_step() == 1
    store.commit([Fact(tag="b", step=5)])
    assert store.next_step() == 6
    store.commit([Fact(tag="c", step=2)])
    assert store.next_step() == 6


def test_seeds_at_minus_one_do_not_advance_the_clock():
    store = Store()
    store.commit([Fact(tag="seed", step=-1)])
    assert store.next_step() == 0


def test_snapshot_is_isolated_from_later_commits():
    store = Store()
    store.commit([Fact(tag="a", step=0)])
    view = store.snapshot()
    store.commit([Fact(tag="b", step=1)])
    assert view.exists("a")
    assert not view.exists("b")


def test_patterns_and_latest_wins():
    store = Store()
    store.commit(
        [
            Fact(tag="draft:1", value="v1", step=0),
            Fact(tag="draft:2", value="v2", step=1),
            Fact(tag="other", step=1),
        ]
    )
    view = store.snapshot()
    assert view.count("draft:*") == 2
    assert [f.tag for f in view.query("draft:1")] == ["draft:1"]
    assert view.value("draft:*") == "v2"
    assert view.get("missing") is None
    assert view.value("missing") is None
