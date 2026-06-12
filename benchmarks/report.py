"""Assemble the results table from out/ records: fixed patterns, random, both oracles,
and (with --selector) the per-task selector row, scored by lookup into the recorded runs.

Usage: uv run --group examples --group bench python benchmarks/report.py \
    --bench gsm8k [--selector]
"""

from __future__ import annotations

import argparse
import asyncio
import json
from collections import Counter
from pathlib import Path

from dotenv import load_dotenv

OUT = Path(__file__).parent / "out"


def load(bench: str, model: str) -> dict[str, dict]:
    records = {}
    for path in sorted(OUT.glob(f"{bench}-*-{model}.json")):
        record = json.loads(path.read_text())
        records[record["pattern"]] = record
    return records


def _tokens(record: dict) -> float | None:
    usage = record.get("usage")
    if not usage:
        return None
    return (usage["input_tokens"] + usage["output_tokens"]) / record["n"]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bench", default="gsm8k")
    parser.add_argument("--model", default="gpt-4o-mini")
    parser.add_argument("--selector", action="store_true")
    args = parser.parse_args()

    records = load(args.bench, args.model)
    if not records:
        raise SystemExit(f"no records for {args.bench}/{args.model} in {OUT}")
    subsamples = {(r["n"], r.get("seed")) for r in records.values()}
    if len(subsamples) > 1:
        raise SystemExit(
            f"records disagree on (n, seed): {sorted(subsamples)}; rerun the matrix"
        )

    # correctness per pattern keyed by task text; tasks aligned across patterns by seed
    correct = {
        p: {it["Input"]: int(it["Correct"]) for it in r["items"]}
        for p, r in records.items()
    }
    tasks = list(next(iter(correct.values())))
    calls = {p: r["llm_calls"] / r["n"] for p, r in records.items()}
    tokens = {p: _tokens(r) for p, r in records.items()}

    rows: list[tuple[str, float, float | None, float | None]] = []
    for p, r in records.items():
        rows.append((p, r["overall"], calls[p], tokens[p]))

    known = [t for t in tokens.values() if t is not None]
    mean_calls = sum(calls.values()) / len(calls)
    mean_tokens = sum(known) / len(known) if len(known) == len(tokens) else None
    random_acc = sum(
        sum(c[t] for c in correct.values()) / len(correct) for t in tasks
    ) / len(tasks)
    rows.append(("random (expected)", random_acc, mean_calls, mean_tokens))

    best_fixed = max(records, key=lambda p: records[p]["overall"])
    rows.append(
        (f"oracle fixed = {best_fixed}", records[best_fixed]["overall"], None, None)
    )

    per_task = sum(max(c[t] for c in correct.values()) for t in tasks) / len(tasks)
    rows.append(("oracle per-task", per_task, None, None))

    if args.selector:
        rows.append(selector_row(tasks, correct, calls, tokens, args.model))

    print(f"\n{args.bench} / {args.model}, n={len(tasks)}\n")
    print(f"{'configuration':>28}  {'acc':>5}  {'calls/task':>10}  {'tok/task':>9}")
    for name, acc, n_calls, n_tokens in rows:
        calls_cell = f"{n_calls:10.1f}" if n_calls is not None else " " * 10
        tok_cell = f"{n_tokens:9.0f}" if n_tokens is not None else " " * 9
        print(f"{name:>28}  {acc:5.2f}  {calls_cell}  {tok_cell}")


def selector_row(
    tasks: list[str],
    correct: dict[str, dict[str, int]],
    calls: dict[str, float],
    tokens: dict[str, float | None],
    model: str,
) -> tuple[str, float, float, float | None]:
    from fedotmas.adapters.pydantic_ai import PydanticAI
    from fedotmas_meta.selector import select

    load_dotenv(Path(__file__).parents[1] / ".env")
    llm = PydanticAI(f"openai-responses:{model}")

    async def pick_all() -> list[str]:
        picks = await asyncio.gather(*(select(t, llm=llm) for t in tasks))
        return [p.pattern for p in picks]

    picks = asyncio.run(pick_all())
    print(f"selector picks: {dict(Counter(picks))}")
    acc = sum(correct[p][t] for p, t in zip(picks, tasks)) / len(tasks)
    cost = sum(calls[p] for p in picks) / len(tasks) + 1  # +1 for the selection call
    picked_tokens = [tokens[p] for p in picks]
    select_tokens = (llm.usage["input_tokens"] + llm.usage["output_tokens"]) / len(
        tasks
    )
    tok = (
        sum(t for t in picked_tokens if t is not None) / len(tasks) + select_tokens
        if all(t is not None for t in picked_tokens)
        else None
    )
    return ("selector (per-task)", acc, cost, tok)


if __name__ == "__main__":
    main()
