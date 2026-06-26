from fedotmas import Rule, action, blackboard, branch, nest
from fedotmas.serialize import to_blueprint


@action
async def research(topic: str) -> str:
    return f"facts about {topic}"


@action
async def write(facts: str) -> str:
    return f"draft from {facts}"


@action
async def triage(issue: str) -> str:
    return "triaged"


@action
async def plan(issue: str) -> str:
    return "planned"


async def count(topic: str) -> int:
    return len(topic.split())


def blueprint_of(flow):
    return to_blueprint(flow.system(entry="in", out="out"))


def main() -> None:
    chain = research + write
    print("flow (no run needed):\n", blueprint_of(chain).model_dump_json(indent=2))

    routed = branch("kind", {"bug": triage, "feature": plan})
    print(
        "\nbranch keeps its declarative select:\n",
        blueprint_of(routed).model_dump_json(indent=2),
    )

    board = blackboard(Rule("count", count, reads="topic", writes="report"))
    composed = research + nest(board, entry="topic", out="report")
    print(
        "\nflow over board recurses into the inner blueprint:\n",
        blueprint_of(composed).model_dump_json(indent=2),
    )


if __name__ == "__main__":
    main()
