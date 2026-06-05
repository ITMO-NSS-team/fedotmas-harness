from dotenv import load_dotenv
from langchain.agents import create_agent as LangChainAgent
from langchain_core.tools import tool
from pydantic_ai import Agent as PydanticAgent

load_dotenv()

MODEL = "openai:gpt-oss-20b"

researcher = PydanticAgent(
    MODEL,
    system_prompt="Given a topic, return 3 concise bullet points with the key facts.",
)


@tool
def word_count(text: str) -> int:
    """Count the number of words in the given text."""
    return len(text.split())


writer = LangChainAgent(
    model=MODEL,
    tools=[word_count],
    system_prompt="Turn the bullet points into one tight paragraph, then report its word count.",
)


if __name__ == "__main__":
    topic = "Heralt of Rivia"
    research = researcher.run_sync(topic)
    print(research)

    result = writer.invoke({"messages": [("user", research.output)]})
    print(result["messages"][-1].content)
