"""Zero-shot probe: can a prompted LLM pick a MAS pattern for a task?

The menu comes from the preset catalog; the pick goes through fedotmas_meta.selector.
"""

import asyncio
from collections import Counter

from dotenv import load_dotenv
from fedotmas.adapters.pydantic_ai import PydanticAI
from fedotmas_meta.selector import select

TASKS = [
    ("What is the capital of Australia?", "single"),
    ("Translate this paragraph into French, keeping the tone.", "single"),
    (
        "Extract the claims from this article, fact-check each, then write a verdict.",
        "chain",
    ),
    (
        "Parse this invoice email, normalize the amounts, and produce a ledger entry.",
        "chain",
    ),
    (
        "Should the city ban cars from the center? Give a balanced recommendation.",
        "debate",
    ),
    (
        "Estimate the number of piano tuners in Berlin; the reasoning must be double-checked.",
        "debate",
    ),
    (
        "Write a product announcement and keep tightening it until it is genuinely punchy.",
        "eval_optimizer",
    ),
    (
        "Draft a contract clause and verify it has no loopholes before returning it.",
        "eval_optimizer",
    ),
    (
        "Compile a market overview of three competitors: pricing, reviews, recent news.",
        "orchestrator",
    ),
    (
        "Summarize this 200-page report into a brief covering finance, risks, operations.",
        "orchestrator",
    ),
    (
        "Handle incoming support tickets: each goes to billing, tech, or general.",
        "router",
    ),
    (
        "Classify each user message as a complaint, a feature request, or praise, and respond accordingly.",
        "router",
    ),
    (
        "Diagnose this production incident from logs, metrics, and deploy history: any of them may hold the clue, and each finding can reopen the others.",
        "blackboard",
    ),
    (
        "Assemble a due-diligence picture of a startup where claims from filings, press, and interviews must cross-check each other until the story is consistent.",
        "blackboard",
    ),
]

REPEATS = 3


async def main() -> None:
    load_dotenv()
    llm = PydanticAI("openai-responses:gpt-4o-mini")
    hits = 0
    for task, expected in TASKS:
        runs = await asyncio.gather(*(select(task, llm=llm) for _ in range(REPEATS)))
        votes = Counter(r.pattern for r in runs)
        picked, _ = votes.most_common(1)[0]
        hit = picked == expected
        hits += hit
        mark = "ok " if hit else "DIFF"
        print(
            f"{mark} {picked:>14} (gold {expected:>14}, votes {dict(votes)})  {task[:60]}"
        )
    print(f"\nagreement with gold: {hits}/{len(TASKS)}")


if __name__ == "__main__":
    asyncio.run(main())
