from __future__ import annotations


def _matches(tag: str, pattern: str) -> bool:
    if pattern.endswith("*"):
        return tag.startswith(pattern[:-1])
    return tag == pattern


def _edges(
    specs: list[tuple[str, list[str], list[str]]],
) -> list[tuple[str, str, str]]:
    """Dataflow edges over (name, reads, writes) node specs: an edge src -> dst via a pattern
    when src writes a tag matching one of dst's read patterns. Self-edges excluded, deduped per
    (src, dst, pattern). Shared by to_graph (observed writes) and to_blueprint (declared)."""
    writers = [(name, tag) for name, _reads, writes in specs for tag in writes]
    seen: set[tuple[str, str, str]] = set()
    edges: list[tuple[str, str, str]] = []
    for name, reads, _writes in specs:
        for pattern in reads:
            for src, tag in writers:
                key = (src, name, pattern)
                if src != name and key not in seen and _matches(tag, pattern):
                    seen.add(key)
                    edges.append((src, name, pattern))
    return edges
