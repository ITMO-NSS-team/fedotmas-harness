"""Evaluator-Optimizer on the EventExecutor with deterministic stub agents."""

import asyncio

from fedotmas.adapters import as_agent
from fedotmas.engine.contract import Fact, Result, View
from fedotmas.engine.executors.event import EventExecutor
from fedotmas.engine.store import Store
from fedotmas.engine.system import System
from fedotmas.engine.terminate import Budget, Goal

THRESHOLD = 3


async def generate(input: object, view: View) -> Result:
    n = view.count("draft:*") + 1
    return Result(payload=n, writes=[Fact(tag=f"draft:{n}", value={"quality": n})])


def generate_trigger(view: View) -> bool:
    verdicts = view.query("verdict:*")
    return not verdicts or not verdicts[-1].value["approved"]


async def critique(input: object, view: View) -> Result:
    n = view.count("draft:*")
    draft = view.get(f"draft:{n}")
    approved = draft.value["quality"] >= THRESHOLD  # type: ignore
    return Result(
        payload=approved,
        writes=[Fact(tag=f"verdict:{n}", value={"approved": approved})],
    )


def critique_trigger(view: View) -> bool:
    return view.count("draft:*") > view.count("verdict:*")


def approved(view: View) -> bool:
    verdicts = view.query("verdict:*")
    return bool(verdicts) and verdicts[-1].value["approved"]


async def main() -> None:
    generator = as_agent(
        generate, name="generator", reads="verdict:*", trigger=generate_trigger
    )
    critic = as_agent(
        critique, name="critic", reads="draft:*", trigger=critique_trigger
    )
    system = System(agents=[generator, critic])
    run = await EventExecutor().run(
        system,
        Store(),
        seed=[Fact(tag="task", value="write a haiku")],
        terminate=Goal(approved) | Budget(max_steps=8),
    )
    for report in run.steps:
        print(
            f"step {report.step}: fired={report.fired} writes={[f.tag for f in report.writes]}"
        )
    print("approved:", approved(run.view))


if __name__ == "__main__":
    asyncio.run(main())
