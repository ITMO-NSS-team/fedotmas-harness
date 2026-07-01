import asyncio

from fedotmas import Outcome, Rule, action, blackboard, run


async def double(x: int) -> int:
    return x * 2


async def triple(x: int) -> int:
    return x * 3


async def grade(draft: str) -> int:
    return len(draft.split())


async def decide(score: int) -> str:
    return "ship" if score >= 5 else "revise"


async def on_flow() -> Outcome:
    return await (action(double) + action(triple)).run(2)


async def on_board() -> Outcome:
    board = blackboard(
        Rule("score", grade, reads="draft", writes="score"),
        Rule(
            "gate", decide, reads="score", writes="verdict", when=["score", "!verdict"]
        ),
    )
    return await board.run({"draft": "a b c d e f"}, goal="verdict")


async def on_system() -> Outcome:
    system = (action(double) + action(triple)).system(entry="in", out="out")
    return await run(system, {"in": 2}, goal="out")


async def main() -> None:
    print("flow.run    ->", (await on_flow()).value)
    print("board.run   ->", (await on_board()).value)
    print("system run  ->", (await on_system()).value)


if __name__ == "__main__":
    asyncio.run(main())
