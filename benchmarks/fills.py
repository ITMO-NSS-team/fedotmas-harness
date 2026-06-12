"""Role fills per benchmark x pattern: the fixed strong filler of the matrix.

One fill per domain, never per task; the task text arrives at run time. Every answer-
producing role must end with only the final answer, to survive exact-match scoring.
"""

ANSWER = (
    "Reason step by step, then give the final answer as a bare number on the last line."
)

FILLS = {
    "gsm8k": {
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
                "one_step": f"Solve this single-step problem directly. {ANSWER}",
                "multi_step": f"Solve this multi-step problem carefully, step by step. {ANSWER}",
            }
        },
        "blackboard": {
            "researcher": "Extract the quantities and relations from the problem.",
            "skeptic": "Check the extraction against the problem text; flag anything wrong or missing.",
            "synthesizer": f"Compute the answer from the verified facts. {ANSWER}",
        },
    },
}
