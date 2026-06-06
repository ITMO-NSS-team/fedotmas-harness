"""Agent contract: the Protocol and message types (Result, Card, Fact, Control, Status, Usage, View)."""

from __future__ import annotations

from enum import Enum
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, Field


class Status(str, Enum):
    OK = "ok"
    ERROR = "error"


class Usage(BaseModel):
    tokens: int = 0
    cost: float = 0.0


class Fact(BaseModel):
    tag: str
    value: Any = None
    producer: str = ""
    step: int = -1
    meta: dict[str, Any] = Field(default_factory=dict)

    @property
    def key(self) -> tuple[str, int]:
        return (self.tag, self.step)


class Control(BaseModel):
    next: str | None = None
    subtasks: list[Any] | None = None
    done: bool = False


class Card(BaseModel):
    name: str
    description: str = ""
    input_schema: dict[str, Any] = Field(default_factory=dict)
    capabilities: list[str] = Field(default_factory=list)


class Result(BaseModel):
    payload: Any = None
    status: Status = Status.OK
    error: str | None = None
    usage: Usage | None = None
    writes: list[Fact] = Field(default_factory=list)
    control: Control | None = None


@runtime_checkable
class View(Protocol):
    def get(self, tag: str) -> Fact | None: ...
    def query(self, pattern: str) -> list[Fact]: ...
    def exists(self, pattern: str) -> bool: ...
    def count(self, pattern: str) -> int: ...


@runtime_checkable
class Agent(Protocol):
    name: str
    reads: str

    def trigger(self, view: View) -> bool: ...
    async def invoke(self, input: Any, view: View) -> Result: ...
    def describe(self) -> Card: ...
