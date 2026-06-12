"""Run the pattern x benchmark matrix; one JSON record file per configuration.

Usage: uv run --group examples --group bench python benchmarks/run_matrix.py \
    --bench gsm8k --n 5 --patterns single,chain
"""

from __future__ import annotations

import argparse
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

os.environ.setdefault("DEEPEVAL_TELEMETRY_OPT_OUT", "YES")

from dotenv import load_dotenv  # noqa: E402
from fedotmas.adapters.pydantic_ai import PydanticAI  # noqa: E402
from fedotmas_meta.presets import get  # noqa: E402
from fills import FILLS  # noqa: E402
from model import FlowModel  # noqa: E402

OUT = Path(__file__).parent / "out"


def bench(name: str, n: int, seed: int):
    """A benchmark over a seeded random subsample of its test split, never a prefix."""
    if name == "gsm8k":
        from datasets import load_dataset
        from deepeval.benchmarks import GSM8K

        suite = GSM8K(n_problems=n, n_shots=0, enable_cot=False)
        data: Any = load_dataset("gsm8k", "main")
        suite.dataset = {
            "train": data["train"],
            "test": data["test"].shuffle(seed=seed),
        }
        return suite
    raise ValueError(f"unknown benchmark {name!r}")


def run_one(pattern: str, args: argparse.Namespace) -> str:
    flow = get(pattern).build(FILLS[args.bench][pattern])
    backend = PydanticAI(f"openai-responses:{args.model}")
    config = FlowModel(f"{pattern}/{args.model}", flow, backend)
    suite = bench(args.bench, args.n, args.seed)
    started = time.time()
    suite.evaluate(model=config)
    record = {
        "bench": args.bench,
        "pattern": pattern,
        "model": args.model,
        "n": args.n,
        "seed": args.seed,
        "overall": suite.overall_score,
        "llm_calls": config.llm.calls,
        "usage": backend.usage,
        "seconds": round(time.time() - started, 1),
        "items": suite.predictions.to_dict("records"),
    }
    path = OUT / f"{args.bench}-{pattern}-{args.model}.json"
    path.write_text(json.dumps(record, ensure_ascii=False, indent=1, default=str))
    return (
        f"{pattern:>14}: score {suite.overall_score:.2f}, "
        f"{config.llm.calls} llm calls, {record['seconds']}s -> {path.name}"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bench", default="gsm8k")
    parser.add_argument("--n", type=int, default=5)
    parser.add_argument("--patterns", default="single")
    parser.add_argument("--model", default="gpt-4o-mini")
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--jobs", type=int, default=1)
    args = parser.parse_args()

    load_dotenv(Path(__file__).parents[1] / ".env")
    OUT.mkdir(exist_ok=True)
    patterns = args.patterns.split(",")

    if args.jobs == 1:
        for pattern in patterns:
            print(run_one(pattern, args))
        return
    bench(args.bench, args.n, args.seed)  # warm the dataset cache once, not per thread
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        futures = {pool.submit(run_one, p, args): p for p in patterns}
        for done in as_completed(futures):
            print(done.result())


if __name__ == "__main__":
    main()
