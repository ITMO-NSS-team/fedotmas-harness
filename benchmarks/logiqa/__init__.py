"""LogiQA: multiple-choice logical-reasoning puzzles, exact match on the option letter.

A hard reasoning probe (models often land ~0.4-0.6) to test whether difficulty-vs-executor,
not model size, opens per-task headroom on a strong model. Clean A-D exact match, no schema
cap. LogiQA's reasoning types are not a partition (one item can carry several), so instead of
the per-category split used by mmlu/mathqa, suite draws a flat seeded sample of the full test
set (deduped by question) -- diversity across types is inherent.

deepeval's LogiQA prompt opens with "Write a multi-choice question for the following article"
(disambiguated only by its few-shot examples); at n_shots=0 that instruction is misleading
noise, so suite strips it -- the input becomes a clean Article/Question/Options/Answer task,
which is what we mean to measure.
"""

from __future__ import annotations

import random
from typing import Any

ANSWER = (
    "Reason step by step, then give the final answer as the bare option letter"
    " (A, B, C, or D) on the last line."
)

FILLS = {
    "single": {"agent": f"Answer the logical-reasoning question. {ANSWER}"},
    "chain": {
        "steps": {
            "analyze": "Restate the premises and what each option claims.",
            "solve": f"Apply the logic and decide which option follows. {ANSWER}",
        }
    },
    "debate": {
        "pro": "Solve the puzzle and defend which option logically follows.",
        "con": "Reason independently; do not assume the other choice is right.",
        "judge": f"Compare the two arguments and pick the option that follows. {ANSWER}",
    },
    "eval_optimizer": {
        "generator": f"Answer the logical-reasoning question. {ANSWER}",
        "critic": "Approve only if the reasoning is logically valid and the option truly follows.",
    },
    "orchestrator": {
        "workers": {
            "analyze": "Lay out the premises and what each option claims.",
            "deduce": "Take the next deductive step the notes call for.",
        },
        "synthesizer": f"From the notes, pick the option that follows. {ANSWER}",
    },
    # personas only (no contested claim about the task): the gsm8k router lesson
    "router": {
        "handlers": {
            "deductive": f"You are a deductive logician. {ANSWER}",
            "critical": f"You are a careful critical thinker. {ANSWER}",
            "systematic": f"You eliminate options systematically. {ANSWER}",
        }
    },
    "blackboard": {
        "researcher": "Extract the premises and what each option claims.",
        "skeptic": "Check each inference against the premises; flag any invalid step.",
        "synthesizer": f"Pick the option the verified reasoning supports. {ANSWER}",
    },
}


def suite(n: int, seed: int) -> Any:
    from deepeval.benchmarks import LogiQA
    from deepeval.benchmarks.logi_qa.task import LogiQATask

    prefix = "Write a multi-choice question for the following article:\n"

    class Seeded(LogiQA):
        _pool: list[Any] | None = None

        def load_benchmark_dataset(self, task: LogiQATask) -> list[Any]:
            if self._pool is None:
                seen: set[str] = set()
                pool: list[Any] = []
                for kind in LogiQATask:
                    for golden in super().load_benchmark_dataset(kind):
                        golden.input = golden.input.replace(prefix, "", 1)
                        if golden.input not in seen:
                            seen.add(golden.input)
                            pool.append(golden)
                random.Random(seed).shuffle(pool)
                self._pool = pool
            return self._pool

    one = next(iter(LogiQATask))
    return Seeded(tasks=[one], n_shots=0, n_problems_per_task=n)
