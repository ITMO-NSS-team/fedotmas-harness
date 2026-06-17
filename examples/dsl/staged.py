import asyncio
import json

from fedotmas import dsl
from fedotmas.engine import View
from fedotmas.sdk import action


@action
async def improve(state: dict, view: View) -> dict:
    return {**state, "draft": state["draft"] + "!"}


@action
async def judge(state: dict, view: View) -> dict:
    return {**state, "approved": state["draft"].endswith("!!!")}


ATOMS = {"improve": improve, "judge": judge}

POOL = dsl.Manifest.model_validate(
    {
        "version": 1,
        "meta": {"name": "eval-optimizer", "intent": "improve a draft until approved"},
        "nodes": {"improve": {"ref": "improve"}, "judge": {"ref": "judge"}},
    }
)

BROKEN_WIRING = dsl.Manifest.model_validate(
    {"version": 1, "flow": {"loop": ["improve", "jugde"], "until": "approved"}}
)

WIRING = dsl.Manifest.model_validate(
    {"version": 1, "flow": {"loop": ["improve", "judge"], "until": "approved"}}
)


async def main() -> None:
    schema = dsl.schema_for_flow(sorted(POOL.nodes))
    closed = [m for m in schema["$defs"]["FlowExpr"]["oneOf"] if "enum" in m]
    print("bare names close over the pool:", json.dumps(closed))

    try:
        dsl.compile(dsl.merge(POOL, BROKEN_WIRING), atoms=ATOMS)
    except dsl.ManifestError as err:
        print("a typo'd wiring comes back as feedback, not a stack trace:")
        for issue in err.issues:
            print(f"  {issue.path}: {issue.message} (expected {issue.expected})")

    flow = dsl.compile(dsl.merge(POOL, WIRING), atoms=ATOMS)
    run = await flow.run({"draft": "v0", "approved": False})
    print("reason:", run.reason)
    print("final:", run.value)


if __name__ == "__main__":
    asyncio.run(main())
