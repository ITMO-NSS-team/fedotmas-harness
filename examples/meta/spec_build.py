from fedotmas.serialize import to_blueprint
from fedotmas_meta import AgentSpec, SystemSpec, assemble


class EchoLLM:
    def __init__(self, tag: str) -> None:
        self.tag = tag

    async def complete(self, prompt, content, view, *, returns=None):
        return f"{self.tag}:{content}"


PROPOSAL = SystemSpec(
    preset="blackboard",
    fill={
        "researcher": AgentSpec(
            prompt="Post the facts the question needs.", model="fast"
        ),
        "skeptic": AgentSpec(prompt="Challenge weak facts.", model="fast"),
        "synthesizer": AgentSpec(
            prompt="Write the final answer.",
            model="strong",
            tools=["search", "https://mcp.run/search/sse"],
        ),
    },
)


def main() -> None:
    wire = PROPOSAL.model_dump_json()
    print("spec is just strings:", SystemSpec.model_validate_json(wire) == PROPOSAL)

    models = {"fast": EchoLLM("fast"), "strong": EchoLLM("strong")}
    flow = assemble(PROPOSAL, models=models, tools={"search": lambda q: q})
    system = flow.system(entry="question", out="answer")

    bp = to_blueprint(system)
    inner = next(n for n in bp.nodes if n.kind == "nest").inner
    roles = sorted(n.name for n in inner.nodes if n.kind == "rule")
    print("built roles:", roles)
    assert roles == ["researcher", "skeptic", "synthesizer"]


if __name__ == "__main__":
    main()
