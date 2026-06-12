"""GSM8K: grade-school math word problems, exact match on the final number.

The domain contract every benchmark folder follows: `suite(n, seed)` returns a deepeval
benchmark over a seeded random subsample of its test split, `FILLS` maps pattern -> role
fill (the fixed strong filler of the matrix).
"""

from __future__ import annotations

from typing import Any

ANSWER = (
    "Reason step by step, then give the final answer as a bare number on the last line."
)

FILLS = {
    "single": {"agent": f"Solve the math word problem step by step. {ANSWER}"},
    "chain": {
        "steps": {
            "extract": "List the quantities given in the problem and what is asked.",
            "solve": f"Carry out the calculation step by step. {ANSWER}",
        }
    },
    "debate": {
        "pro": "Solve the problem step by step and state your answer.",
        "con": "Solve the problem independently, step by step; do not assume the other solution is right.",
        "judge": f"Compare the two solutions and pick the correct one. {ANSWER}",
    },
    "eval_optimizer": {
        "generator": f"Solve the problem step by step. {ANSWER}",
        "critic": "Approve only if every arithmetic step and the final number are correct.",
    },
    "orchestrator": {
        "workers": {
            "extract": "Pull out the quantities and relations the problem states.",
            "compute": "Do the next calculation the notes call for.",
        },
        "synthesizer": f"From the notes, give the answer. {ANSWER}",
    },
    "router": {
        "handlers": {
            "one_step": f"This problem needs one calculation; find it and check it. {ANSWER}",
            "multi_step": f"This problem needs several dependent steps; track intermediate values carefully. {ANSWER}",
        }
    },
    "blackboard": {
        "researcher": "Extract the quantities and relations from the problem.",
        "skeptic": "Check the extraction against the problem text; flag anything wrong or missing.",
        "synthesizer": f"Compute the answer from the verified facts. {ANSWER}",
    },
}


def suite(n: int, seed: int) -> Any:
    from datasets import load_dataset
    from deepeval.benchmarks import GSM8K

    s = GSM8K(n_problems=n, n_shots=0, enable_cot=False)
    # the namespaced id, or an unlucky cwd resolves "gsm8k" to this very folder
    data: Any = load_dataset("openai/gsm8k", "main")
    s.dataset = {"train": data["train"], "test": data["test"].shuffle(seed=seed)}
    return s
