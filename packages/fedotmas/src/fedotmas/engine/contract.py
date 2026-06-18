from __future__ import annotations

from enum import Enum
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, Field


class Status(str, Enum):
    OK = "ok"
    ERROR = "error"


Key = tuple[str, int, str]


class Fact(BaseModel):
    tag: str
    value: Any = None
    producer: str = ""
    step: int = -1
    meta: dict[str, Any] = Field(default_factory=dict)

    @property
    def key(self) -> Key:
        """Version identity, (tag, step, producer). Producer is part of it: two nodes writing
        the same tag in the same superstep produce two distinct versions, not one."""
        return (self.tag, self.step, self.producer)


class Card(BaseModel):
    name: str
    description: str = ""
    meta: dict[str, Any] = Field(default_factory=dict)


class Result(BaseModel):
    status: Status = Status.OK
    error: str | None = None
    writes: list[Fact] = Field(default_factory=list)


@runtime_checkable
class View(Protocol):
    """Read access to the store. `query/exists/count` take a pattern, an exact tag or a `*`
    prefix glob; `get/value` take a pattern too and return the latest match."""

    def get(self, tag: str) -> Fact | None: ...
    def value(self, tag: str) -> Any: ...
    def query(self, pattern: str) -> list[Fact]: ...
    def exists(self, pattern: str) -> bool: ...
    def count(self, pattern: str) -> int: ...


@runtime_checkable
class Node(Protocol):
    """The unit the executor runs. `reads` is one or more whitespace-separated fact patterns
    and carries double duty: the facts matched by it are the node's input (invoke receives
    them as a list[Fact]), and their keys are the node's re-fire identity. The executor is edge-triggered: a node fires at most once per
    distinct set of matched facts, however long `trigger` stays true. A node with empty reads
    therefore fires at most once per run; a node meant to re-fire on new facts must name them
    in `reads`.
    """

    name: str
    reads: str

    def trigger(self, view: View) -> bool: ...
    async def invoke(self, input: Any, view: View) -> Result: ...
    def describe(self) -> Card: ...
