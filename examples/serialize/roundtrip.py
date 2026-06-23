# flow surface (flow = research + write); entry/out are the default ports "in"/"out", and the
# wiring between leaves is implied by `seq`, not stored as tags:
#   {
#     "surface": "flow", "entry": "in", "out": "out",
#     "root": {"op": "seq", "steps": [
#       {"op": "leaf", "kind": "action", "name": "research", "ref": "research"},
#       {"op": "leaf", "kind": "action", "name": "write", "ref": "write"}
#     ]},
#     "requires": ["research", "write"]
#   }
#
# board surface (the two rules below); a missing `when` means produce-once, `goal` is the target
# tag, `when` keeps the engine's own ["tag", "!absent"] syntax:
#   {
#     "surface": "board", "goal": "verdict",
#     "rules": [
#       {"name": "score", "reads": "draft", "writes": "score",
#        "body": {"kind": "action", "ref": "score"}},
#       {"name": "gate", "reads": "score", "writes": "verdict",
#        "when": ["score", "!verdict"],
#        "body": {"kind": "action", "ref": "gate"}}
#     ],
#     "requires": ["score", "gate"]
#   }
#
# Open field decision (flagged, not locked): whether entry/out (flow) and goal (board) live in the
# manifest as shown, or stay run-args passed to .run().

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
