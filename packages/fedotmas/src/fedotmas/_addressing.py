from __future__ import annotations

from dataclasses import dataclass


def build_id(hint: str, n: int) -> str:
    return f"{hint}#{n}"


def base_of(name: str) -> str:
    """The authoring hint behind a minted id, the build counter stripped: the key a rebuilt
    node's body is looked up by (serialize.Deps.bodies)."""
    return name.split("#", 1)[0]


def alias(out: str) -> str:
    return f"alias:{out}"


@dataclass(frozen=True)
class Loop:
    """The names a loop mints from its base: the synthetic iter/done nodes and the dataflow tags
    they wire (state versions under `state`, the body's `body_in`/`body_out`). `of` recovers the
    base from either synthetic node. Shared by the flow compiler and serialize.from_blueprint so
    a minted name and the parse that recovers it cannot drift."""

    base: str

    @property
    def iter(self) -> str:
        return f"{self.base}:iter"

    @property
    def done(self) -> str:
        return f"{self.base}:done"

    @property
    def state(self) -> str:
        return f"{self.base}:s"

    @property
    def body_in(self) -> str:
        return f"{self.base}:in"

    @property
    def body_out(self) -> str:
        return f"{self.base}:out"

    @classmethod
    def of(cls, node_name: str) -> Loop:
        return cls(node_name.removesuffix(":iter").removesuffix(":done"))


@dataclass(frozen=True)
class Branch:
    """The names a branch mints from its base: the route node, each case's inlet tag and each
    case's join node. `of` recovers the base from the route node. Shared like Loop."""

    base: str

    @property
    def route(self) -> str:
        return f"{self.base}:route"

    def inlet(self, case: str) -> str:
        return f"{self.base}:in:{case}"

    def join(self, case: str) -> str:
        return f"{self.base}:join:{case}"

    @classmethod
    def of(cls, node_name: str) -> Branch:
        return cls(node_name.removesuffix(":route"))
