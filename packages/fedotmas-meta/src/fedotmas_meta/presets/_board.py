"""Internal: the code-backed blackboard preset.

No coordinator and no document form: rules self-activate over shared state, nest() folds
the board into one typed Flow so the run surface stays uniform with the data families.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fedotmas.sdk import Flow, Rule, blackboard, nest

from fedotmas_meta.presets._spec import Fill, RoleSpec, check_fill


@dataclass(frozen=True)
class BoardPreset:
    name: str
    hint: str
    roles: tuple[RoleSpec, ...]

    def build(self, roles: Fill) -> Flow[Any, Any]:
        fill = check_fill(self.name, self.roles, roles)
        board = blackboard(
            Rule(
                "researcher",
                prompt=fill["researcher"],
                reads="question",
                writes="facts",
            ),
            Rule(
                "skeptic",
                prompt=fill["skeptic"],
                reads="facts",
                writes="review",
                input="Question: {question}\n\nFacts:\n{input}",
            ),
            Rule(
                "synthesizer",
                prompt=fill["synthesizer"],
                reads="review",
                when=("facts", "review"),
                writes="answer",
                input="Question: {question}\n\nFacts:\n{facts}\n\nReview:\n{review}",
            ),
        )
        return nest(board, entry="question", out="answer")


BLACKBOARD = BoardPreset(
    name="blackboard",
    hint="no coordinator: specialists react to shared state until an answer settles",
    roles=(
        RoleSpec("researcher", "posts the facts the question needs"),
        RoleSpec("skeptic", "challenges weak facts"),
        RoleSpec("synthesizer", "writes the final answer once the dust settles"),
    ),
)
