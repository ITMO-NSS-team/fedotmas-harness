"""Concrete backends for the SDK's LLM seam, one module per framework, gated by extras.

Nothing here is imported by the core. To wrap your own framework: implement the LLM protocol
(sdk.atoms) for a model backend, or engine.as_node for a whole agent as an engine Node.
"""
