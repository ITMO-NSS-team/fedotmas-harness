import asyncio

from fedotmas import Flow, Hooks, Rule, action, blackboard, nest


async def double(x: int) -> int:
    return x * 2


async def triple(x: int) -> int:
    return x * 3


class Trace(Hooks):
    async def on_run_start(self, system):
        print("start:", len(system.nodes), "nodes")

    async def on_step(self, report):
        print(f"step {report.step}: {report.fired} -> {[f.tag for f in report.writes]}")

    def on_run_end(self, run):
        print("end:", run.status, run.reason)


class Meter(Hooks):
    def __init__(self) -> None:
        self.steps = 0
        self.facts = 0

    async def on_step(self, report):
        self.steps += 1
        self.facts += len(report.writes)


class Scoped(Hooks):
    async def on_run_start(self, system, scope):
        print(f"{'  ' * len(scope)}> enter {scope or ('root',)}")

    async def on_run_end(self, run, scope):
        print(f"{'  ' * len(scope)}< leave {scope or ('root',)}: {run.value}")


async def observe() -> None:
    meter = Meter()
    await (action(double) + action(triple)).run(2, hooks=[Trace(), meter])
    print("metered:", meter.steps, "steps,", meter.facts, "facts")


async def scoped() -> None:
    inner = blackboard(Rule("inner", double, reads="seed", writes="out"))
    solve: Flow[int, int] = nest(inner, entry="seed", out="out")
    await (action(triple) + solve).run(3, hooks=[Scoped()])


async def main() -> None:
    await observe()
    await scoped()


if __name__ == "__main__":
    asyncio.run(main())
