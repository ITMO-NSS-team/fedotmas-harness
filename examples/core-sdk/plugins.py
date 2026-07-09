import asyncio

from fedotmas import Flow, Plugin, Rule, action, blackboard, nest
from fedotmas.engine import Fact, Result
from fedotmas.ext.plugins import Retry, Timeout


async def double(x: int) -> int:
    return x * 2


async def triple(x: int) -> int:
    return x * 3


async def flaky(x: int) -> int:
    return x + 1


class Trace(Plugin):  # observer: watches the run/step hooks, returns nothing
    async def before_run(self, system, view, scope):
        print("start:", len(system.nodes), "nodes")

    async def after_step(self, report):
        print(f"step {report.step}: {report.fired} -> {[f.tag for f in report.writes]}")

    async def after_run(self, run):
        print("end:", run.status, run.reason)


class Meter(Plugin):  # observer: state on the instance, keyed per node if concurrent
    def __init__(self) -> None:
        self.steps = 0
        self.facts = 0

    async def after_step(self, report):
        self.steps += 1
        self.facts += len(report.writes)


class Clamp(Plugin):  # interceptor: return a new value to change it, facts are frozen
    def __init__(self, ceiling: int) -> None:
        self.ceiling = ceiling

    async def before_node(self, node, input, view):
        return [
            f.model_copy(update={"value": min(f.value, self.ceiling)}) for f in input
        ]


class Fallback(Plugin):  # interceptor: around_node holds `call`, so it can substitute
    def __init__(self, value) -> None:
        self.value = value

    async def around_node(self, node, input, view, call):
        try:
            return await call(input, view)
        except Exception:
            return Result(writes=[Fact(tag=node.name, value=self.value)])


class Alarm(Plugin):  # event: fires only when it happens, never mutates
    async def on_error(self, node, error, view):
        print("error in", node.name, "->", error.value, f"({error.meta.get('type')})")


class Scoped(Plugin):  # scope rides on the carriers: a parameter in, a field out
    async def before_run(self, system, view, scope):
        print(f"{'  ' * len(scope)}> enter {scope or ('root',)}")

    async def after_run(self, run):
        print(f"{'  ' * len(run.scope)}< leave {run.scope or ('root',)}")


async def observe() -> None:
    meter = Meter()
    await (action(double) + action(triple)).run(2, plugins=[Trace(), meter])
    print("metered:", meter.steps, "steps,", meter.facts, "facts")


async def mix() -> None:
    # one list, one type: observers, interceptors, events. first is outermost
    await (action(flaky) + action(double)).run(5, plugins=[Retry(3), Clamp(4), Alarm()])


async def ready_made() -> None:
    # common interceptors ship in fedotmas.ext.plugins, so around_node is
    # rarely hand-written
    await action(double).run(1, plugins=[Retry(3, on=TimeoutError), Timeout(5.0)])


async def scoped() -> None:
    # observer hooks follow the nested run (tell the levels apart by scope);
    # interceptors like Retry wrap the nest node once, they never multiply inside
    inner = blackboard(Rule("inner", double, reads="seed", writes="out"))
    solve: Flow[int, int] = nest(inner, entry="seed", out="out")
    await (action(triple) + solve).run(3, plugins=[Scoped()])


async def main() -> None:
    await observe()
    await mix()
    await ready_made()
    await scoped()


if __name__ == "__main__":
    asyncio.run(main())
