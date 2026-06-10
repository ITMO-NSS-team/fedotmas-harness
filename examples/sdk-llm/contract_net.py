"""Contract-Net (P14): bidders contend for one task, an auction policy awards the winner.

The rule surface plus a runtime Policy. Every contractor's rule is ready on an open task, but
AuctionSelect fires only the highest bidder, so just the winner spends a model call and writes
the result. The bid is a property of the agent; the policy is orthogonal to the agents, handed
to the executor at run time.

Needs an OpenAI key in .env. Run: uv run --group examples python examples/sdk-llm/contract_net.py
"""

import asyncio

from dotenv import load_dotenv

from fedotmas.adapters.pydantic_ai import PydanticAI
from fedotmas.engine.contract import Fact, View
from fedotmas.engine.executor import ReactiveExecutor
from fedotmas.engine.policy import AuctionSelect
from fedotmas.engine.store import Store
from fedotmas.engine.terminate import Goal
from fedotmas.sdk import Rule, blackboard

llm = PydanticAI("openai-responses:gpt-4o-mini")

BIDS = {"generalist": 0.3, "domain_expert": 0.9, "fast_cheap": 0.5}


def bidder(name: str) -> Rule:
    async def execute(task: str, view: View) -> str:
        return await llm.complete(
            f"You are the '{name}' contractor. Complete the task concisely.", task, view
        )

    return Rule(name, execute, writes="result", reads="task", meta={"bid": BIDS[name]})


async def main() -> None:
    load_dotenv()
    net = blackboard(*(bidder(n) for n in BIDS))
    store = Store()
    stream = ReactiveExecutor().stream(
        net,
        store,
        seed=[
            Fact(tag="task", value="draft a migration plan from a monolith to services")
        ],
        terminate=Goal(lambda v: v.exists("result")),
        policy=AuctionSelect(key=lambda a, v: a.describe().meta["bid"]),
    )
    async for r in stream:
        print(f"step {r.step}: {r.fired} -> {[f.tag for f in r.writes]}")
    print("winner:", max(BIDS, key=lambda n: BIDS[n]))
    print("result:", store.snapshot().value("result"))


if __name__ == "__main__":
    asyncio.run(main())
