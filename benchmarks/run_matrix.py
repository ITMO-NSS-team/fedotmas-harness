"""Run the pattern x benchmark matrix.

Usage:
uv run --group examples --group bench python benchmarks/run_matrix.py \
    --bench gsm8k --n 5 --patterns blackboard
"""

from __future__ import annotations

import argparse
import importlib
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from types import ModuleType

os.environ.setdefault("DEEPEVAL_TELEMETRY_OPT_OUT", "YES")

from dotenv import load_dotenv  # noqa: E402

OUT = Path(__file__).parent / "out"


def slug(model: str) -> str:
    return model.replace(":", "-").replace("/", "-")


def run_one(pattern: str, domain: ModuleType, args: argparse.Namespace) -> str:
    raise NotImplementedError


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bench", default="gsm8k")
    parser.add_argument("--n", type=int, default=5)
    parser.add_argument("--patterns", default="single")
    parser.add_argument("--model", default="openrouter:openai/gpt-oss-20b")
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--jobs", type=int, default=1)
    parser.add_argument(
        "--out", default="", help="subdir under out/ for this run's records"
    )
    args = parser.parse_args()

    load_dotenv(Path(__file__).parents[1] / ".env")
    domain = importlib.import_module(args.bench)
    patterns = args.patterns.split(",")

    if args.jobs == 1:
        for pattern in patterns:
            print(run_one(pattern, domain, args))
        return
    domain.suite(args.n, args.seed)  # warm the dataset cache once, not per thread
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        futures = {pool.submit(run_one, p, domain, args): p for p in patterns}
        for done in as_completed(futures):
            print(done.result())


if __name__ == "__main__":
    main()
