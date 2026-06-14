"""MathQA: harder multiple-choice math across categories, exact match on the option letter.

A harder stress test than gsm8k/mmlu (multi-step quantitative reasoning) to see whether
difficulty-vs-executor, not just model size, opens per-task headroom on a strong model.
Five categories split the --n budget evenly (n // 5 each, keep n divisible by 5).

Note: deepeval scores MathQA against a 4-letter schema (a-d), but questions carry a fifth
option (often "e) none of these"); "e" answers are unrepresentable and count wrong for every
pattern alike, so the pattern comparison stays fair while absolute accuracy is capped.
"""

from __future__ import annotations

import random
from typing import Any

ANSWER = "Reason step by step, then give the final answer as the bare option letter on the last line."

GROUPS = ("probability", "geometry", "physics", "gain", "general")

FILLS = {
    "single": {"agent": f"Solve the multiple-choice math problem. {ANSWER}"},
    "chain": {
        "steps": {
            "extract": "List the quantities given and what each option claims.",
            "solve": f"Carry out the calculation and pick the option. {ANSWER}",
        }
    },
    "debate": {
        "pro": "Solve the problem step by step and state which option is correct.",
        "con": "Solve it independently, step by step; do not assume the other option is right.",
        "judge": f"Compare the two solutions and pick the correct option. {ANSWER}",
    },
    "eval_optimizer": {
        "generator": f"Solve the problem step by step and pick the option. {ANSWER}",
        "critic": "Approve only if every arithmetic step and the chosen option are correct.",
    },
    "orchestrator": {
        "workers": {
            "extract": "Pull out the quantities and relations the problem states.",
            "compute": "Do the next calculation the notes call for.",
        },
        "synthesizer": f"From the notes, pick the option. {ANSWER}",
    },
    # personas mirror GROUPS; the routing label is the observable topic, not a contested fact
    "router": {
        "handlers": {
            "probability": f"You are a probabilist. {ANSWER}",
            "geometry": f"You are a geometer. {ANSWER}",
            "physics": f"You are a physicist. {ANSWER}",
            "finance": f"You are a financial analyst. {ANSWER}",
            "general": f"You are a mathematician. {ANSWER}",
        }
    },
    "blackboard": {
        "researcher": "Extract the quantities and what each option claims.",
        "skeptic": "Check the extraction and arithmetic; flag anything wrong or missing.",
        "synthesizer": f"Pick the option the verified work supports. {ANSWER}",
    },
}


def suite(n: int, seed: int) -> Any:
    from deepeval.benchmarks import MathQA
    from deepeval.benchmarks.math_qa.task import MathQATask

    class Seeded(MathQA):
        def load_benchmark_dataset(self, task: MathQATask) -> list[Any]:
            goldens = super().load_benchmark_dataset(task)
            random.Random(seed).shuffle(goldens)
            return goldens

    tasks = [MathQATask(group) for group in GROUPS]
    return Seeded(tasks=tasks, n_shots=0, n_problems_per_task=n // len(tasks))
