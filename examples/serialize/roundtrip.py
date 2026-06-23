# Contract-first (TDD red): this pins the serialize / deserialize API before it exists.
# `fedotmas.serialize` is intentionally unimplemented, so the import below does not resolve
# and the type-checker flags it. That is the point: this file is the executable spec the
# module must satisfy, written before a line of it.
#
# Proposed surface, three names:
#   to_manifest(obj)         Flow | Board -> Manifest   the authored system, as data
#   from_manifest(manifest)  Manifest -> Flow | Board   the authored system, rebuilt
#   Manifest                 a pydantic model; JSON is native (.model_dump_json / .model_validate_json)
#
# The law: from_manifest(to_manifest(x)) runs the same as x. Code bodies cannot be serialized, so
# to_manifest turns each leaf body into a by-ref key (its node name), collected in manifest.requires;
# the rebuilt system re-binds them at run via bind=. So a pure-code flow that bound nothing needs
# bind after a round-trip: that asymmetry is the logical / physical seam made visible.

import asyncio

from fedotmas import Rule, action, blackboard
from fedotmas.engine.contract import View
from fedotmas.serialize import (  # unimplemented on purpose
    Manifest,
    from_manifest,
    to_manifest,
)


@action
async def research(topic: str) -> str:
    return f"facts about {topic}"


@action
async def write(facts: str) -> str:
    return f"draft from {facts}"


async def flow_roundtrip() -> None:
    flow = research + write
    original = await flow.run("haiku")  # pure code: binds nothing

    manifest: Manifest = to_manifest(flow)
    assert manifest.surface == "flow"
    assert set(manifest.requires) == {"research", "write"}  # bodies are now by-ref

    wire = manifest.model_dump_json(indent=2)  # Manifest -> JSON, via pydantic
    print("flow manifest:\n", wire)

    clone = from_manifest(
        Manifest.model_validate_json(wire)
    )  # JSON -> Manifest -> Flow
    # the clone holds refs, not code, so the bodies must be re-supplied to run
    out = await clone.run("haiku", bind={"research": research, "write": write})
    assert out.ok, (out.reason, out.errors)
    assert out.value == original.value  # the round-trip law


async def board_roundtrip() -> None:
    async def score(draft: str, view: View) -> int:
        return len(draft.split())

    async def gate(n: int, view: View) -> str:
        return "ship" if n >= 5 else "revise"

    board = blackboard(
        Rule("score", score, reads="draft", writes="score"),
        Rule("gate", gate, reads="score", writes="verdict", when=["score", "!verdict"]),
    )
    seed = {"draft": "a quick brown fox jumps"}
    original = await board.run(seed, goal="verdict")

    manifest: Manifest = to_manifest(board)
    assert manifest.surface == "board"
    assert set(manifest.requires) == {"score", "gate"}

    clone = from_manifest(Manifest.model_validate_json(manifest.model_dump_json()))
    out = await clone.run(seed, goal="verdict", bind={"score": score, "gate": gate})
    assert out.ok and out.value == original.value  # the round-trip law


async def main() -> None:
    await flow_roundtrip()
    await board_roundtrip()
    print("round-trip holds for both surfaces")


if __name__ == "__main__":
    asyncio.run(main())
