from __future__ import annotations

from enum import Enum
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, Field


class Status(str, Enum):
    OK = "ok"
    ERROR = "error"


class Kind(str, Enum):
    """The closed set of floor node-kinds a Card declares. Extensions add their own kind
    strings (Card.kind stays an open `str`); these are the ones the core surfaces stamp."""

    ACTION = "action"
    GATHER = "gather"
    INTO = "into"
    MERGE = "merge"
    ALIAS = "alias"
    NEST = "nest"
    RULE = "rule"
    BRANCH_ROUTE = "branch.route"
    BRANCH_JOIN = "branch.join"
    LOOP_ITER = "loop.iter"
    LOOP_DONE = "loop.done"


Key = tuple[str, int, str]


class Fact(BaseModel):
    """One entry in the store: a `tag` naming the value, the `value` itself, and the provenance
    the engine stamps on write (`producer` node, `step` clock). `meta` carries side data, e.g.
    an error's traceback. The store keeps every version; `key` is the identity that separates
    them."""

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
    """A node's self-description for introspection: name, doc, meta (e.g. an auction bid a
    Policy reads back), and the declarative portrait the executor never reads: kind, reads,
    writes, params. Factories stamp what they already hold; the engine still learns real writes
    by running, so a Card declares but is never trusted (see serialize.to_blueprint). `system`
    holds a live sub-system (nest, loop) for a walker to recurse into, excluded from dumps."""

    name: str
    description: str = ""
    meta: dict[str, Any] = Field(default_factory=dict)
    kind: str = Kind.ACTION
    reads: list[str] = Field(default_factory=list)
    writes: list[str] = Field(default_factory=list)
    params: dict[str, Any] = Field(default_factory=dict)
    system: Any = Field(default=None, exclude=True)


class Result(BaseModel):
    """What a node returns from invoke: the facts it `writes` (stamped by the engine before
    they land), or `status=ERROR` with a message. The writes are committed at the end of the
    superstep, so a node never sees its own output within the same step."""

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
