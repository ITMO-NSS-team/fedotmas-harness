"""Fact identity and the Store: keys, the logical clock, snapshot isolation, patterns."""

from fedotmas.engine import Fact, Store
from fedotmas.engine.contract import matches
from fedotmas.engine.store import Snapshot


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


def test_snapshot_takes_no_copy():
    store = Store()
    store.commit([Fact(tag="a", step=0)])
    snap = store.snapshot()
    assert isinstance(snap, Snapshot)
    assert snap._facts is store._facts


def test_snapshot_isolates_versions_of_the_same_tag():
    store = Store()
    store.commit([Fact(tag="t", value=1, step=0)])
    view = store.snapshot()
    store.commit([Fact(tag="t", value=2, step=1)])
    assert view.count("t") == 1
    assert view.value("t") == 1
    assert store.snapshot().count("t") == 2
    assert store.snapshot().value("t") == 2


def test_cutoff_bounds_glob_paths_too():
    store = Store()
    store.commit([Fact(tag="s:1", step=0), Fact(tag="r", step=0)])
    early = store.snapshot()
    store.commit([Fact(tag="s:2", step=1), Fact(tag="q:9", step=1)])
    assert early.count("s:*") == 1
    assert not early.exists("s:2")
    assert not early.exists("q:*")
    assert [f.tag for f in early.query("*")] == ["s:1", "r"]


def test_glob_preserves_insertion_order_across_tags():
    store = Store()
    store.commit(
        [
            Fact(tag="a:1", step=0),
            Fact(tag="b:1", step=0),
            Fact(tag="a:2", step=1),
            Fact(tag="b:2", step=1),
        ]
    )
    view = store.snapshot()
    assert [f.tag for f in view.query("*")] == ["a:1", "b:1", "a:2", "b:2"]
    assert [f.tag for f in view.query("a:*")] == ["a:1", "a:2"]


def test_every_view_operation_agrees_with_a_linear_scan():
    committed: list[Fact] = []
    store = Store()
    for k in range(4):
        batch = [
            Fact(tag=f"state:{k}", value=k, step=k),
            Fact(tag="reply", value=k, step=k),
        ]
        committed.extend(batch)
        store.commit(batch)
    view = store.snapshot()
    for pattern in ("state:2", "state:*", "reply", "missing", "missing:*", "*"):
        expected = [f for f in committed if matches(f.tag, pattern)]
        assert [f.key for f in view.query(pattern)] == [f.key for f in expected]
        assert view.exists(pattern) == bool(expected)
        assert view.count(pattern) == len(expected)
        assert view.get(pattern) == (expected[-1] if expected else None)
        assert view.value(pattern) == (expected[-1].value if expected else None)
