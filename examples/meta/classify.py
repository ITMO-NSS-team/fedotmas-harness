"""Zero-shot probe: can a prompted LLM pick a MAS pattern for a task?"""

import asyncio
from collections import Counter

from dotenv import load_dotenv
from fedotmas import sdk
from fedotmas.adapters.pydantic_ai import PydanticAI

PATTERNS = {
    "single": "one agent answers directly; the task is small and self-contained",
    "chain": "fixed pipeline of specialized steps, each consuming the previous output",
    "debate": "parallel agents argue or vote; contested judgement or error-prone reasoning",
    "eval_optimizer": "generator improves a draft in a loop until a critic approves",
    "orchestrator": "a planner splits the task into runtime-sized subtasks done in parallel",
    "router": "incoming items are dispatched to one of several specialist handlers",
}

MENU = "\n".join(f"- {name}: {hint}" for name, hint in PATTERNS.items())

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
]

REPEATS = 3

select = sdk.agent(
    "select",
    prompt=(
        "You design multi-agent systems. Pick the execution pattern that best fits the"
        f" task you are given. Patterns:\n{MENU}"
    ),
    labels=list(PATTERNS),
)


async def main() -> None:
    load_dotenv()
    llm = PydanticAI("openai-responses:gpt-4o-mini")
    hits = 0
    for task, expected in TASKS:
        runs = await asyncio.gather(
            *(select.run(task, llm=llm) for _ in range(REPEATS))
        )
        votes = Counter(r.value for r in runs)
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
