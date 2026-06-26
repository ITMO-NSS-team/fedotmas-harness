import asyncio

from fedotmas import Condition, Rule, action, blackboard


async def grade(draft: str) -> int:
    return len(draft.split())


async def decide(score: int) -> str:
    return "ship" if score >= 5 else "revise"


async def revise(state: dict) -> dict:
    n = state["score"] + 1
    return {"score": n, "done": n >= 3}


async def main() -> None:
    produce_once = Rule("score", grade, reads="draft", writes="score")
    tag_presence = Rule(
        "gate", decide, reads="score", writes="verdict", when=["score", "!verdict"]
    )
    board = blackboard(produce_once, tag_presence)
    verdict = await board.run({"draft": "a b c d e f"}, goal="verdict")
    print("when=:", verdict.value)

    by_key = action(revise).loop(until="done")
    by_condition = action(revise).loop(until=Condition(key="score", op="gte", value=3))
    by_callable = action(revise).loop(until=lambda s: s["score"] >= 3)
    for name, flow in [
        ("key", by_key),
        ("condition", by_condition),
        ("callable", by_callable),
    ]:
        out = await flow.run({"score": 0})
        print(f"until {name}:", out.value)


if __name__ == "__main__":
    asyncio.run(main())
