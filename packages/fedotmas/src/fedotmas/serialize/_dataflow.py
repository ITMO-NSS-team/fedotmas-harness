from __future__ import annotations

from fedotmas.engine.store import matches


def _edges(
    specs: list[tuple[str, list[str], list[str]]],
) -> list[tuple[str, str, str]]:
    """Dataflow edges over (name, reads, writes) node specs: an edge src -> dst via a pattern
    when src writes a tag matching one of dst's read patterns. Self-edges excluded, deduped per
    (src, dst, pattern). Shared by to_graph (observed writes) and to_blueprint (declared)."""
    writers = [(name, tag) for name, _reads, writes in specs for tag in writes]
    return list(
        dict.fromkeys(
            (src, name, pattern)
            for name, reads, _writes in specs
            for pattern in reads
            for src, tag in writers
            if src != name and matches(tag, pattern)
        )
    )
