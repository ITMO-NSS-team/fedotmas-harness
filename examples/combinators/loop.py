"""loop: a body iterates in versioned rounds until a gate predicate holds.

Two-step body (generate then critique), same shape as engine/eval_optimizer.py. A
one-step body would be the Reflection pattern. The combinator owns the round versioning,
the feedback edge from the gate back to the head, and the until gate. The head step
refines the artifact, the tail step produces the gate value.
"""

import asyncio
from typing import Any, cast

from fedotmas.dsl.combinators import loop
from fedotmas.engine.contract import Fact, View
from fedotmas.engine.executor import ReactiveExecutor
from fedotmas.engine.store import Store
from fedotmas.engine.terminate import Budget, Goal

THRESHOLD = 3


async def generate(feedback: Any, view: View) -> dict:
    prev = feedback if isinstance(feedback, dict) else {}
    quality = cast(int, prev.get("quality", 0)) + 1
    return {"draft": f"v{quality}", "quality": quality}


async def critique(draft: Any, view: View) -> dict:
    q = cast(int, draft["quality"])
    return {"approved": q >= THRESHOLD, "quality": q}


def approved(verdict: Any, view: View) -> bool:
    return isinstance(verdict, dict) and bool(verdict.get("approved"))


async def main() -> None:
    system = loop(generate, critique, until=approved, entry="task", out="draft")
    store = Store()
    stream = ReactiveExecutor().stream(
        system,
        store,
        seed=[Fact(tag="task", value="write a haiku")],
        terminate=Goal(lambda v: v.exists("draft")) | Budget(max_steps=12),
    )
    async for r in stream:
        print(f"step {r.step}: {r.fired} -> {[f.tag for f in r.writes]}")
    print("draft:", store.snapshot().value("draft"))


if __name__ == "__main__":
    asyncio.run(main())
