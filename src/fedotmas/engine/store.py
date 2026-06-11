"""Store: the shared blackboard. Commit facts, snapshot an immutable view, query it.

The store owns the logical clock: `next_step` is one past the highest step ever committed,
so the step axis is monotonic across runs and mid-run feeders, and re-running an executor
over the same store cannot collide fact keys. Seeds at step -1 sit before time and do not
advance it.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

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

    def value(self, tag: str) -> Any:
        f = self.get(tag)
        return f.value if f else None

    def exists(self, pattern: str) -> bool:
        return any(_match(f.tag, pattern) for f in self._facts)

    def count(self, pattern: str) -> int:
        return len(self.query(pattern))


class Store:
    def __init__(self) -> None:
        self._facts: list[Fact] = []
        self._clock = 0

    def commit(self, facts: Iterable[Fact]) -> None:
        for f in facts:
            self._facts.append(f)
            if f.step >= self._clock:
                self._clock = f.step + 1

    def next_step(self) -> int:
        return self._clock

    def snapshot(self) -> View:
        return Snapshot(tuple(self._facts))
