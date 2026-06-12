"""MMLU: multiple-choice questions across diverse subjects, exact match on the letter.

Five subjects split the --n budget evenly (n // 5 each, so keep n divisible by 5);
the seeded shuffle happens inside each subject's test split.
"""

from __future__ import annotations

import random
from typing import Any

ANSWER = (
    "Reason step by step, then give the final answer as the bare option letter"
    " (A, B, C, or D) on the last line."
)

GROUPS = (
    "high_school_mathematics",
    "formal_logic",
    "moral_disputes",
    "astronomy",
    "professional_law",
)

FILLS = {
    "single": {"agent": f"Answer the multiple-choice question. {ANSWER}"},
    "chain": {
        "steps": {
            "analyze": "Restate what the question asks and what each option claims.",
            "solve": f"Decide which option is correct. {ANSWER}",
        }
    },
    "debate": {
        "pro": "Answer the question and defend your choice of option.",
        "con": "Answer independently; do not assume the other choice is right.",
        "judge": f"Compare the two argued choices and pick the correct one. {ANSWER}",
    },
    "eval_optimizer": {
        "generator": f"Answer the multiple-choice question. {ANSWER}",
        "critic": "Approve only if the reasoning is sound and the chosen option is correct.",
    },
    "orchestrator": {
        "workers": {
            "analyze": "Lay out what the question asks and what each option claims.",
            "decide": "Weigh the options against the analysis and pick one.",
        },
        "synthesizer": f"From the notes, give the answer. {ANSWER}",
    },
    # personas mirror GROUPS; the routing label is the observable subject, never
    # a contested property of the task (the gsm8k router lesson)
    "router": {
        "handlers": {
            "math": f"You are a mathematician. {ANSWER}",
            "logic": f"You are a logician. {ANSWER}",
            "ethics": f"You are an ethicist. {ANSWER}",
            "science": f"You are an astronomer. {ANSWER}",
            "law": f"You are a lawyer. {ANSWER}",
        }
    },
    "blackboard": {
        "researcher": "Lay out what the question asks and what each option claims.",
        "skeptic": "Check the analysis against the question; flag anything wrong or missing.",
        "synthesizer": f"Pick the option the verified analysis supports. {ANSWER}",
    },
}


def suite(n: int, seed: int) -> Any:
    from deepeval.benchmarks import MMLU
    from deepeval.benchmarks.mmlu.task import MMLUTask

    class Seeded(MMLU):
        def load_benchmark_dataset(self, task: MMLUTask) -> list[Any]:
            goldens = super().load_benchmark_dataset(task)
            random.Random(seed).shuffle(goldens)
            return goldens

    tasks = [MMLUTask(group) for group in GROUPS]
    return Seeded(tasks=tasks, n_shots=0, n_problems_per_task=n // len(tasks))
