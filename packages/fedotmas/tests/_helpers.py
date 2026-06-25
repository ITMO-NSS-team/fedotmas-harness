"""Shared bodies and dataflow-assertion helpers for the serialize tests (graph + blueprint)."""

from fedotmas.engine.contract import Fact
from fedotmas.engine.executor import ReactiveExecutor
from fedotmas.engine.store import Store
from fedotmas.engine.terminate import Budget, Goal


async def double(x):
    return x * 2


async def triple(x):
    return x * 3


async def pick_a(s):
    return "A"


async def pick_b(s):
    return "B"


async def bump(s):
    n = s["n"] + 1
    return {"n": n, "done": n >= 3}


async def score(d):
    return len(d.split())


async def gate(n):
    return "ship" if n >= 5 else "revise"


async def upper(s):
    return s.upper()


async def count(topic):
    return len(topic.split())


async def run_flow(flow, value):
    """Compile a flow to its `out` and run it, returning (system, run) for projection."""
    system = flow.system(entry="in", out="out")
    run = await ReactiveExecutor().run(
        system,
        Store(),
        seed=[Fact(tag="in", value=value)],
        terminate=Goal(lambda v: v.exists("out")) | Budget(50),
    )
    return system, run


def node(projection, name):
    """The node named `name` in a Graph or Blueprint."""
    return next(n for n in projection.nodes if n.name == name)


def has_edge(projection, src, dst):
    return any(e.src == src and e.dst == dst for e in projection.edges)
