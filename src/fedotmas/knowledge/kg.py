"""KGoT Implementation https://github.com/spcl/knowledge-graph-of-thoughts"""

"""
Key idea:

Instead of running the entire intermediate CoT (or unimportant steps) directly
through LLM, the system iteratively extracts relevant knowledge from the task
and structures it in an algorithmic knowledge graph (KG). This graph is then
enriched with tools. This structured representation of tasks  allows weak models
to solve complex problems while minimizing hallucinations and noise.
"""
