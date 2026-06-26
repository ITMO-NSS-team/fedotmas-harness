import asyncio

from fedotmas.engine import as_node
from fedotmas.engine.contract import Fact, Result, View
from fedotmas.engine.executor import ReactiveExecutor
from fedotmas.engine.store import Store
from fedotmas.engine.system import System
from fedotmas.engine.terminate import Budget, Goal

THRESHOLD = 3


async def generate(input: object, view: View) -> Result:
    n = view.count("draft:*") + 1
    return Result(writes=[Fact(tag=f"draft:{n}", value={"quality": n})])


def generate_trigger(view: View) -> bool:
    verdicts = view.query("verdict:*")
    return not verdicts or not verdicts[-1].value["approved"]


async def critique(input: object, view: View) -> Result:
    n = view.count("draft:*")
    approved = view.value(f"draft:{n}")["quality"] >= THRESHOLD
    return Result(
        writes=[Fact(tag=f"verdict:{n}", value={"approved": approved})],
    )


def critique_trigger(view: View) -> bool:
    return view.count("draft:*") > view.count("verdict:*")


def approved(view: View) -> bool:
    verdicts = view.query("verdict:*")
    return bool(verdicts) and verdicts[-1].value["approved"]


async def main() -> None:
    generator = as_node(
        generate, name="generator", reads="verdict:*", trigger=generate_trigger
    )
    critic = as_node(critique, name="critic", reads="draft:*", trigger=critique_trigger)
    system = System(nodes=[generator, critic])
    store = Store()
    stream = ReactiveExecutor().stream(
        system,
        store,
        seed=[Fact(tag="task", value="write a haiku")],
        terminate=Goal(approved) | Budget(max_steps=8),
    )
    async for report in stream:
        print(
            f"step {report.step}: fired={report.fired} writes={[f.tag for f in report.writes]}"
        )
    print("approved:", approved(store.snapshot()))


if __name__ == "__main__":
    asyncio.run(main())
