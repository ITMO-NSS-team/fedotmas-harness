"""Store: the shared blackboard. Snapshot, commit, query, subscribe."""

from __future__ import annotations

from collections.abc import Iterable

from fedotmas.engine.contract import Fact, View


def _match(tag: str, pattern: str) -> bool:
    if pattern.endswith("*"):
        return tag.startswith(pattern[:-1])
    return tag == pattern


class Snapshot:
    def __init__(self, facts: tuple[Fact, ...]) -> None:
        self._facts = facts

    def query(self, pattern: str) -> list[Fact]:
        return [f for f in self._facts if _match(f.tag, pattern)]

    def get(self, tag: str) -> Fact | None:
        found = self.query(tag)
        return found[-1] if found else None

    def exists(self, pattern: str) -> bool:
        return any(_match(f.tag, pattern) for f in self._facts)

    def count(self, pattern: str) -> int:
        return len(self.query(pattern))


class Store:
    def __init__(self) -> None:
        self._facts: list[Fact] = []

    def commit(self, facts: Iterable[Fact]) -> None:
        self._facts.extend(facts)

    def snapshot(self) -> View:
        return Snapshot(tuple(self._facts))
