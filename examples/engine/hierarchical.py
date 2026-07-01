import asyncio

from fedotmas.engine import (
    Card,
    Fact,
    Goal,
    ReactiveExecutor,
    Result,
    Store,
    System,
    View,
    as_node,
)


async def search_a(input: object, view: View) -> Result:
    return Result(writes=[Fact(tag="found:a", value=f"a({view.value('task')})")])


async def search_b(input: object, view: View) -> Result:
    return Result(writes=[Fact(tag="found:b", value=f"b({view.value('task')})")])


async def summarize(input: object, view: View) -> Result:
    parts = [f.value for f in view.query("found:*")]
    return Result(writes=[Fact(tag="summary", value=" & ".join(parts))])


RESEARCH_TEAM = System(
    nodes=[
        as_node(search_a, name="searcher_a", reads="task"),
        as_node(search_b, name="searcher_b", reads="task"),
        as_node(
            summarize,
            name="summarizer",
            reads="found:*",
            trigger=lambda v: v.count("found:*") == 2,
        ),
    ]
)


class Team:
    def __init__(self, name: str, system: System, *, reads: str, out: str) -> None:
        self.name = name
        self.reads = reads
        self._system = system
        self._out = out

    def trigger(self, view: View) -> bool:
        return view.exists(self.reads) and not view.exists(self._out)

    async def invoke(self, input: object, view: View) -> Result:
        inner = Store()
        run = await ReactiveExecutor().run(
            self._system,
            inner,
            seed=[Fact(tag="task", value=view.value(self.reads))],
            terminate=Goal(lambda v: v.exists("summary")),
        )
        return Result(writes=[Fact(tag=self._out, value=run.view.value("summary"))])

    def describe(self) -> Card:
        return Card(name=self.name)


async def finalize(input: object, view: View) -> Result:
    return Result(
        writes=[Fact(tag="report", value=f"REPORT: {view.value('team_out')}")]
    )


async def main() -> None:
    system = System(
        nodes=[
            Team("research_team", RESEARCH_TEAM, reads="brief", out="team_out"),
            as_node(finalize, name="finalizer", reads="team_out"),
        ]
    )
    store = Store()
    stream = ReactiveExecutor().stream(
        system,
        store,
        seed=[Fact(tag="brief", value="witcher lore")],
        terminate=Goal(lambda v: v.exists("report")),
    )
    async for r in stream:
        print(f"step {r.step}: {r.fired} -> {[f.tag for f in r.writes]}")
    print("report:", store.snapshot().value("report"))


if __name__ == "__main__":
    asyncio.run(main())
