"""Node contract: the Protocol and message types (Result, Card, Fact, Status, View).

The unit of execution is a Node, not an "agent": the engine does not care whether a node
wraps an LLM agent, a plain function, or a whole sub-system, and the SDK reserves the word
agent for the LLM-backed atom specifically.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, Field


class Status(str, Enum):
    OK = "ok"
    ERROR = "error"


class Fact(BaseModel):
    tag: str
    value: Any = None
    producer: str = ""
    step: int = -1
    meta: dict[str, Any] = Field(default_factory=dict)

    @property
    def key(self) -> tuple[str, int]:
        return (self.tag, self.step)


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
    def get(self, tag: str) -> Fact | None: ...
    def value(self, tag: str) -> Any: ...
    def query(self, pattern: str) -> list[Fact]: ...
    def exists(self, pattern: str) -> bool: ...
    def count(self, pattern: str) -> int: ...


@runtime_checkable
class Node(Protocol):
    name: str
    reads: str

    def trigger(self, view: View) -> bool: ...
    async def invoke(self, input: Any, view: View) -> Result: ...
    def describe(self) -> Card: ...
