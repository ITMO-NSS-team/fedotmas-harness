from _presets import CATALOG
from fedotmas.serialize import to_blueprint
from fedotmas_meta import AgentSpec, SystemSpec, assemble


class EchoLLM:
    def __init__(self, tag: str) -> None:
        self.tag = tag

    async def complete(self, prompt, input, view, returns=None, tools=None):
        return f"{self.tag}:{input}"


VOTERS = {
    "optimist": AgentSpec(prompt="Argue the upside.", model="fast"),
    "skeptic": AgentSpec(prompt="Attack the weakest assumption.", model="fast"),
    "pragmatist": AgentSpec(prompt="Weigh cost against payoff.", model="strong"),
}

PROPOSAL = SystemSpec(
    preset="debate",
    fill={
        "voters": VOTERS,
        "judge": AgentSpec(prompt="Read the votes and decide.", model="strong"),
    },
)


def main() -> None:
    wire = PROPOSAL.model_dump_json()
    print("spec is just strings:", SystemSpec.model_validate_json(wire) == PROPOSAL)

    models = {"fast": EchoLLM("fast"), "strong": EchoLLM("strong")}
    flow = assemble(PROPOSAL, presets=CATALOG, models=models)
    system = flow.system(entry="question", out="answer")

    bp = to_blueprint(system)
    agents = {n.name.split("#")[0] for n in bp.nodes if n.kind == "action"}
    print("debaters:", sorted(agents))
    assert set(VOTERS) <= agents
    assert "judge" in agents


if __name__ == "__main__":
    main()
