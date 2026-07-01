import asyncio

from fedotmas import action, branch, run
from fedotmas.serialize import Blueprint, Deps, from_blueprint, to_blueprint


async def double(x: int) -> int:
    return x * 2


async def triple(x: int) -> int:
    return x * 3


async def pick_a(state: dict) -> str:
    return "A"


async def pick_b(state: dict) -> str:
    return "B"


async def _out(system, seed_tag, value, goal):
    out = await run(system, {seed_tag: value}, goal=goal)
    return out.value


async def rebuild_and_check(system, bodies, value, *, seed_tag="in", goal="out"):
    wire = to_blueprint(system).model_dump_json()
    rebuilt = from_blueprint(Blueprint.model_validate_json(wire), Deps(bodies=bodies))
    same_shape = to_blueprint(rebuilt) == to_blueprint(system)
    same_output = await _out(rebuilt, seed_tag, value, goal) == await _out(
        system, seed_tag, value, goal
    )
    return {"same_shape": same_shape, "same_output": same_output}


async def main() -> None:
    chain = (action(double) + action(triple)).system(entry="in", out="out")
    print(
        "chain:",
        await rebuild_and_check(chain, {"double": double, "triple": triple}, 2),
    )

    routed = branch("kind", {"x": action(pick_a), "y": action(pick_b)}).system(
        entry="in", out="out"
    )
    print(
        "branch (declarative select survives):",
        await rebuild_and_check(
            routed, {"pick_a": pick_a, "pick_b": pick_b}, {"kind": "y"}
        ),
    )


if __name__ == "__main__":
    asyncio.run(main())
