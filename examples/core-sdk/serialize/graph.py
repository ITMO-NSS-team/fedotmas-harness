import asyncio

from fedotmas import Rule, action, blackboard, nest
from fedotmas.engine.contract import Fact
from fedotmas.engine.executor import ReactiveExecutor
from fedotmas.engine.store import Store
from fedotmas.engine.terminate import Budget, Goal
from fedotmas.serialize import to_graph


@action
async def research(topic: str) -> str:
    return f"facts about {topic}"


@action
async def write(facts: str) -> str:
    return f"draft from {facts}"


async def count(topic: str) -> int:
    return len(topic.split())


async def graph_of(flow, value):
    system = flow.system(entry="in", out="out")
    run = await ReactiveExecutor().run(
        system,
        Store(),
        seed=[Fact(tag="in", value=value)],
        terminate=Goal(lambda v: v.exists("out")) | Budget(50),
    )
    return to_graph(system, run)


async def main() -> None:
    flow = research + write
    print("flow:\n", (await graph_of(flow, "haiku")).model_dump_json(indent=2))

    board = blackboard(Rule("count", count, reads="topic", writes="report"))
    composed = research + nest(board, entry="topic", out="report")
    print(
        "\nboard is subset of flow:\n",
        (await graph_of(composed, "tea")).model_dump_json(indent=2),
    )


if __name__ == "__main__":
    asyncio.run(main())
