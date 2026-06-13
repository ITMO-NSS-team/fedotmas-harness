venv:
    uv sync
    cp -n .env.example .env 2>/dev/null || true

venv-dev:
    uv sync --group dev
    uv run prek install
    @echo "Dev environment ready"

# --- benchmark repeats -------------------------------------------------------
# run-0 already exists in out/.out_<bench>_gpt4omini-0; add runs 1 and 2 for n=3.
# Same seed: repeats measure model stochasticity on the same 100 tasks.

bench_models := "openrouter:meta-llama/llama-3.1-8b-instruct openrouter:mistralai/ministral-8b-2512 openrouter:openai/gpt-oss-20b"
bench_patterns := "single,chain,debate,eval_optimizer,orchestrator,blackboard"
_be := "uv run --group examples --group bench python benchmarks"

# One repeat of a bench across all three models into run dir RUN (e.g. 1, 2).
bench-run bench run jobs="6":
    #!/usr/bin/env bash
    set -euo pipefail
    for m in {{bench_models}}; do
        echo ">> {{bench}} run {{run}}: $m"
        {{_be}}/run_matrix.py --bench {{bench}} --n 100 --seed 7 --jobs {{jobs}} \
            --patterns {{bench_patterns}} --model "$m" \
            --out .out_{{bench}}_gpt4omini-{{run}}
    done

# Mean ± std over all run dirs for one model (pass selector=--selector for the live row).
bench-agg bench model selector="":
    {{_be}}/report.py --bench {{bench}} --model "{{model}}" \
        --runs '.out_{{bench}}_gpt4omini-*' {{selector}}

# Offline mean ± std tables for all three models of a bench.
bench-agg-all bench:
    #!/usr/bin/env bash
    set -euo pipefail
    for m in {{bench_models}}; do just bench-agg {{bench}} "$m"; done
