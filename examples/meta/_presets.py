"""The preset menu these examples assemble against. Presets are content the caller owns, not
package mechanism, so the examples carry the pair they demonstrate and pass it to assemble."""

from __future__ import annotations

from fedotmas import Flow, blackboard, gather, nest
from fedotmas_llm import PromptRule, agent
from fedotmas_meta import Preset, ResolvedFill, RoleSpec, group, solo


class BoardPreset:
    """A blackboard nested as one node: researcher -> skeptic -> synthesizer over shared facts."""

    name = "blackboard"
    hint = "no coordinator: specialists react to shared state until an answer settles"
    roles = (
        RoleSpec("researcher", "posts the facts the question needs"),
        RoleSpec("skeptic", "challenges weak facts"),
        RoleSpec("synthesizer", "writes the final answer once the dust settles"),
    )
    reserved = frozenset[str]()

    def build(self, fill: ResolvedFill) -> Flow:
        researcher = solo(fill["researcher"])
        skeptic = solo(fill["skeptic"])
        synthesizer = solo(fill["synthesizer"])
        board = blackboard(
            PromptRule(
                "researcher",
                prompt=researcher.prompt,
                llm=researcher.llm,
                tools=list(researcher.tools) or None,
                reads="question",
                writes="facts",
            ),
            PromptRule(
                "skeptic",
                prompt=skeptic.prompt,
                llm=skeptic.llm,
                tools=list(skeptic.tools) or None,
                reads="facts",
                writes="review",
                input="Question: {question}\n\nFacts:\n{input}",
            ),
            PromptRule(
                "synthesizer",
                prompt=synthesizer.prompt,
                llm=synthesizer.llm,
                tools=list(synthesizer.tools) or None,
                reads="review",
                when=("facts", "review"),
                writes="answer",
                input="Question: {question}\n\nFacts:\n{facts}\n\nReview:\n{review}",
            ),
        )
        return nest(board, entry="question", out="answer")


class DebatePreset:
    """No shared state: voters answer in parallel, then a judge reads the votes and decides."""

    name = "debate"
    hint = (
        "no shared state: voters argue in parallel, a judge reads the votes and decides"
    )
    roles = (
        RoleSpec("voters", "the debaters, each arguing one side", many=True),
        RoleSpec("judge", "reads the votes and writes the verdict"),
    )
    reserved = frozenset({"judge", "question", "answer"})

    def build(self, fill: ResolvedFill) -> Flow:
        voters = group(fill["voters"])
        judge = solo(fill["judge"])
        panel = gather(
            *(
                agent(
                    name,
                    prompt=b.prompt,
                    llm=b.llm,
                    tools=list(b.tools) or None,
                    input="Question: {input}",
                )
                for name, b in voters.items()
            )
        )
        decide = agent(
            "judge",
            prompt=judge.prompt,
            takes=list[str],
            returns=str,
            llm=judge.llm,
            tools=list(judge.tools) or None,
            input="Votes:\n{input}",
        )
        return panel + decide


CATALOG: tuple[Preset, ...] = (BoardPreset(), DebatePreset())
