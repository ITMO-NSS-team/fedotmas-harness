from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fedotmas import Flow, blackboard, nest
from fedotmas_llm import PromptRule

from fedotmas_meta.presets._spec import Fill, RoleSpec, check_fill


@dataclass(frozen=True)
class BoardPreset:
    """A preset whose body is a blackboard, nested as one typed flow node. The fixed roles
    wire researcher -> skeptic -> synthesizer over shared facts; build fills their prompts."""

    name: str
    hint: str
    roles: tuple[RoleSpec, ...]

    def build(self, roles: Fill) -> Flow[Any, Any]:
        fill = check_fill(self.name, self.roles, roles)
        board = blackboard(
            PromptRule(
                "researcher",
                prompt=fill["researcher"],
                reads="question",
                writes="facts",
            ),
            PromptRule(
                "skeptic",
                prompt=fill["skeptic"],
                reads="facts",
                writes="review",
                input="Question: {question}\n\nFacts:\n{input}",
            ),
            PromptRule(
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
