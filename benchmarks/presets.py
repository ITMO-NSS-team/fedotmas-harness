"""The pattern catalog the benchmark matrix runs against. These presets used to live in the
package; they are content, not mechanism, so each consumer (here, the examples, the tests)
owns the menu it needs and passes it to assemble/select."""

from __future__ import annotations

from typing import Any

from fedotmas import Flow, blackboard, gather, nest
from fedotmas_llm import PromptRule, agent
from fedotmas_meta import (
    AgentSpec,
    Preset,
    ResolvedFill,
    RoleSpec,
    SystemSpec,
    group,
    solo,
)


class BoardPreset:
    """A blackboard nested as one typed node: researcher -> skeptic -> synthesizer over shared
    facts. build fills their prompts; the wiring is fixed."""

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
    """No shared state: every voter answers in parallel, then a judge reads the gathered votes
    and decides. `voters` is a many role (keys name the debaters), `judge` the single arbiter."""

    name = "debate"
    hint = (
        "no shared state: voters argue in parallel, a judge reads the votes and decides"
    )
    roles = (
        RoleSpec("voters", "the debaters, each arguing one side", many=True),
        RoleSpec("judge", "reads the votes and writes the verdict"),
    )
    # the names build() puts on the wiring: the judge node plus the system boundary tags
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


def get(name: str) -> Preset:
    for p in CATALOG:
        if p.name == name:
            return p
    raise KeyError(f"unknown preset {name!r}; one of {[p.name for p in CATALOG]}")


def lift(fill: dict[str, Any]) -> dict[str, Any]:
    """Lift an old-style fill (prompt strings, or name -> prompt dicts) into AgentSpec form."""
    return {
        role: {k: AgentSpec(prompt=v) for k, v in value.items()}
        if isinstance(value, dict)
        else AgentSpec(prompt=value)
        for role, value in fill.items()
    }


def spec(pattern: str, fills: dict[str, Any]) -> SystemSpec:
    """The SystemSpec a pattern resolves to under a domain's fills: the preset name plus each
    role's prompt. The proposal run_matrix assembles and the selector reads in full."""
    return SystemSpec(preset=pattern, fill=lift(fills[pattern]))
