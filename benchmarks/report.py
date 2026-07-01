"""Assemble the results table from recorded runs.

Single run (default): one dir → fixed patterns, random, both oracles, and with --selector
the live per-task selector row, scored by lookup into that dir's records.

    uv run --group examples --group bench python benchmarks/report.py --bench gsm8k

Aggregate (--runs GLOB): several run dirs of the same (bench, model) → per-cell mean ± std,
plus a stable per-task oracle (a task counts only for the fraction of runs some pattern got
it right), which deflates the single-run luck that inflates the per-run oracle.

    uv run --group examples --group bench python benchmarks/report.py \
        --bench gsm8k --model openrouter:mistralai/ministral-8b-2512 \
        --runs '.out_gsm8k_gpt4omini-*'
"""

from __future__ import annotations

import argparse
import asyncio
import importlib
import json
from collections import Counter
from pathlib import Path
from statistics import mean, stdev
from typing import TYPE_CHECKING

from dotenv import load_dotenv

if TYPE_CHECKING:
    from fedotmas_llm import LLM
    from fedotmas_meta import SystemSpec

OUT = Path(__file__).parent / "out"
ORDER = (
    "single",
    "chain",
    "debate",
    "eval_optimizer",
    "orchestrator",
    "blackboard",
    "router",
)


def load(directory: Path, bench: str, model: str) -> dict[str, dict]:
    slug = model.replace(":", "-").replace("/", "-")
    records = {}
    for path in sorted(directory.glob(f"{bench}-*-{slug}.json")):
        record = json.loads(path.read_text())
        records[record["pattern"]] = record
    return records


def _tokens(record: dict) -> float | None:
    usage = record.get("usage")
    if not usage:
        return None
    return (usage["input_tokens"] + usage["output_tokens"]) / record["n"]


def metrics(records: dict[str, dict]) -> dict:
    """Pure per-run metrics; no I/O, no LLM. `correct[pattern][task]` is 0/1, tasks aligned
    across patterns by the fixed seed so the oracles and selector can index by task text."""
    subsamples = {(r["n"], r.get("seed")) for r in records.values()}
    if len(subsamples) > 1:
        raise SystemExit(f"records disagree on (n, seed): {sorted(subsamples)}")
    correct = {
        p: {it["Input"]: int(it["Correct"]) for it in r["items"]}
        for p, r in records.items()
    }
    tasks = list(next(iter(correct.values())))
    best = max(records, key=lambda p: records[p]["overall"])
    return {
        "n": len(tasks),
        "tasks": tasks,
        "correct": correct,
        "acc": {p: r["overall"] for p, r in records.items()},
        "calls": {p: r["llm_calls"] / r["n"] for p, r in records.items()},
        "tok": {p: _tokens(r) for p, r in records.items()},
        "random": sum(sum(c[t] for c in correct.values()) / len(correct) for t in tasks)
        / len(tasks),
        "oracle_fixed": (best, records[best]["overall"]),
        "oracle_pertask": sum(max(c[t] for c in correct.values()) for t in tasks)
        / len(tasks),
    }


def _fmt(values: list[float], width: int = 5, prec: int = 2) -> str:
    cell = f"{mean(values):.{prec}f}"
    if len(values) > 1:
        cell += f"±{stdev(values):.{prec}f}"
    return f"{cell:>{width}}"


def single(directory: Path, args: argparse.Namespace) -> None:
    records = load(directory, args.bench, args.model)
    if not records:
        raise SystemExit(f"no records for {args.bench}/{args.model} in {directory}")
    m = metrics(records)
    rows = [(p, m["acc"][p], m["calls"][p], m["tok"][p]) for p in records]
    known = [t for t in m["tok"].values() if t is not None]
    rows.append(
        (
            "random (expected)",
            m["random"],
            mean(m["calls"].values()),
            mean(known) if len(known) == len(m["tok"]) else None,
        )
    )
    rows.append(
        (f"oracle fixed = {m['oracle_fixed'][0]}", m["oracle_fixed"][1], None, None)
    )
    rows.append(("oracle per-task", m["oracle_pertask"], None, None))
    if args.selector:
        fills = importlib.import_module(args.bench).FILLS
        rows.append(selector_row(m, args.selector_model, fills))

    print(f"\n{args.bench} / {args.model}, n={m['n']}\n")
    print(f"{'configuration':>28}  {'acc':>5}  {'calls/task':>10}  {'tok/task':>9}")
    for name, acc, n_calls, n_tokens in rows:
        calls_cell = f"{n_calls:10.1f}" if n_calls is not None else " " * 10
        tok_cell = f"{n_tokens:9.0f}" if n_tokens is not None else " " * 9
        print(f"{name:>28}  {acc:5.2f}  {calls_cell}  {tok_cell}")


def aggregate(dirs: list[Path], args: argparse.Namespace) -> None:
    runs = [load(d, args.bench, args.model) for d in dirs]
    runs = [r for r in runs if r]
    if not runs:
        raise SystemExit(f"no records for {args.bench}/{args.model} under {args.runs}")
    ms = [metrics(r) for r in runs]
    patterns = [p for p in ORDER if any(p in m["acc"] for m in ms)]

    print(f"\n{args.bench} / {args.model}, {len(ms)} runs x n={ms[0]['n']}\n")
    print(f"{'configuration':>28}  {'acc':>11}  {'tok/task':>9}")
    for p in patterns:
        accs = [m["acc"][p] for m in ms if p in m["acc"]]
        toks = [m["tok"][p] for m in ms if m["tok"].get(p) is not None]
        tok = f"{mean(toks):9.0f}" if toks else " " * 9
        print(f"{p:>28}  {_fmt(accs, 11)}  {tok}")
    print(f"{'random (expected)':>28}  {_fmt([m['random'] for m in ms], 11)}")
    print(f"{'oracle fixed':>28}  {_fmt([m['oracle_fixed'][1] for m in ms], 11)}")
    print(
        f"{'oracle per-task (per run)':>28}  {_fmt([m['oracle_pertask'] for m in ms], 11)}"
    )
    print(f"{'oracle per-task (stable)':>28}  {stable_oracle(ms):11.2f}")

    if args.selector:
        fills = importlib.import_module(args.bench).FILLS
        accs = [selector_row(m, args.selector_model, fills)[1] for m in ms]
        print(f"{'selector (per-task)':>28}  {_fmt(accs, 11)}")


def stable_oracle(ms: list[dict]) -> float:
    """Per task, the best pattern's mean correctness across runs (a pattern that won once by
    luck contributes its true hit-rate, not 1.0). The honest, reproducible per-task ceiling."""
    tasks = ms[0]["tasks"]
    patterns = ms[0]["correct"].keys()
    total = 0.0
    for t in tasks:
        total += max(
            mean(m["correct"][p][t] for m in ms if p in m["correct"]) for p in patterns
        )
    return total / len(tasks)


_SELECT_PROMPT = (
    "You design multi-agent systems. Each candidate is given as its full system spec — the"
    " preset and every agent's prompt. Pick the one that best fits the task.\n{menu}"
)


async def select_on_specs(task: str, specs: dict[str, SystemSpec], llm: LLM) -> str:
    """Pick a pattern by its full SystemSpec — the preset and every agent's prompt, the same
    proposal a meta-agent emits. The benchmark's selection over the serialized system rather
    than a hand-written hint; labels stay the pattern names so the recorded-correctness lookup
    is unchanged."""
    from fedotmas_llm import agent

    menu = "\n".join(
        f"- {name}:\n{s.model_dump_json(indent=2)}" for name, s in specs.items()
    )
    pick = agent("select", prompt=_SELECT_PROMPT.format(menu=menu), labels=list(specs))
    run = await pick.run(task, bind={"llm": llm})
    if not run.ok:
        raise RuntimeError(f"selection failed: {run.reason}")
    return run.value


def selector_row(
    m: dict, model: str, fills: dict
) -> tuple[str, float, float, float | None]:
    from fedotmas_llm.adapters.pydantic_ai import PydanticAI
    from presets import spec

    load_dotenv(Path(__file__).parents[1] / ".env")
    llm = PydanticAI(model)
    correct, tasks, calls, tokens = m["correct"], m["tasks"], m["calls"], m["tok"]
    # menu is each recorded pattern's full spec; labels stay names so the lookup resolves
    specs = {p: spec(p, fills) for p in correct}

    async def pick_all() -> list[str]:
        picks = await asyncio.gather(*(select_on_specs(t, specs, llm) for t in tasks))
        return list(picks)

    picks = asyncio.run(pick_all())
    print(f"selector picks: {dict(Counter(picks))}")
    acc = sum(correct[p][t] for p, t in zip(picks, tasks)) / len(tasks)
    cost = sum(calls[p] for p in picks) / len(tasks) + 1  # +1 for the selection call
    picked = [tokens[p] for p in picks]
    select_tok = (llm.usage.input_tokens + llm.usage.output_tokens) / len(tasks)
    tok = (
        sum(t for t in picked if t is not None) / len(tasks) + select_tok
        if all(t is not None for t in picked)
        else None
    )
    return ("selector (per-task)", acc, cost, tok)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bench", default="gsm8k")
    parser.add_argument("--model", default="gpt-oss-20b")
    parser.add_argument("--selector", action="store_true")
    # the selector is part of our system: one fixed model across all benchmark models
    parser.add_argument("--selector-model", default="openai-responses:gpt-4o-mini")
    parser.add_argument(
        "--out", default="", help="single-run subdir under out/ to read"
    )
    parser.add_argument(
        "--runs", default="", help="glob of run dirs under out/ to aggregate"
    )
    args = parser.parse_args()

    if args.runs:
        aggregate(sorted(p for p in OUT.glob(args.runs) if p.is_dir()), args)
    else:
        single(OUT / args.out, args)


if __name__ == "__main__":
    main()
