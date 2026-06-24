# Results

> **Regenerating these results is temporarily unavailable** during the dsl/serialization refactor: the dsl-based flow patterns were removed from `fedotmas_meta.presets`. Check out commit `2bd05ed` (the last with the dsl) to re-run `benchmarks/run_matrix.py`; the numbers below were produced there.

n = 100, seed = 7, 3 runs per cell (mean±sd). Executor = model column. Selector judge = fixed gpt-4o-mini. Random = analytic expected accuracy of a uniform pattern pick. Best fixed = the single best pattern's mean accuracy (one pattern committed across runs). Oracle per-task = stable per-item argmax across runs. MathQA absolute accuracy is capped (~20% of items carry a 5th option the scoring schema cannot express).

## Accuracy

### GSM8K

| configuration | gpt-oss-20b | ministral-8b | llama-3.1-8b |
|---|---|---|---|
| single | 0.94±0.02 | 0.94±0.01 | 0.80±0.05 |
| chain | 0.84±0.01 | 0.90±0.02 | 0.61±0.07 |
| debate | 0.89±0.02 | 0.95±0.01 | 0.61±0.05 |
| eval_optimizer | 0.95±0.01 | 0.95±0.01 | 0.75±0.04 |
| orchestrator | 0.90±0.01 | 0.80±0.02 | 0.69±0.02 |
| blackboard | 0.95±0.01 | 0.90±0.02 | 0.60±0.04 |
| random (expected) | 0.91±0.00 | 0.91±0.00 | 0.67±0.00 |
| best fixed | 0.95 (blackboard) | 0.95 (debate) | 0.80 (single) |
| oracle per-task | 0.98 | 0.96 | 0.92 |
| selector | 0.89 | 0.94 | 0.74 |

### MMLU

| configuration | gpt-oss-20b | ministral-8b | llama-3.1-8b |
|---|---|---|---|
| single | 0.89±0.02 | 0.83±0.01 | 0.63±0.01 |
| chain | 0.89±0.02 | 0.78±0.02 | 0.58±0.02 |
| debate | 0.88±0.02 | 0.83±0.01 | 0.61±0.01 |
| eval_optimizer | 0.89±0.01 | 0.81±0.02 | 0.65±0.05 |
| orchestrator | 0.82±0.06 | 0.79±0.02 | 0.59±0.02 |
| blackboard | 0.88±0.02 | 0.82±0.02 | 0.61±0.08 |
| random (expected) | 0.87±0.00 | 0.81±0.00 | 0.61±0.01 |
| best fixed | 0.89 (eval_optimizer) | 0.83 (debate) | 0.65 (eval_optimizer) |
| oracle per-task | 0.95 | 0.90 | 0.84 |
| selector | 0.88 | 0.78 | 0.63 |

### MathQA

| configuration | gpt-oss-20b |
|---|---|
| single | 0.73±0.01 |
| chain | 0.70±0.01 |
| debate | 0.70±0.03 |
| eval_optimizer | 0.70±0.01 |
| orchestrator | 0.71±0.02 |
| blackboard | 0.69±0.03 |
| random (expected) | 0.71±0.00 |
| best fixed | 0.73 (single) |
| oracle per-task | 0.74 |
| selector | — |

### LogiQA

| configuration | gpt-oss-20b |
|---|---|
| single | 0.77±0.04 |
| chain | 0.64±0.04 |
| debate | 0.76±0.04 |
| eval_optimizer | 0.79±0.01 |
| orchestrator | 0.70±0.02 |
| blackboard | 0.72±0.02 |
| random (expected) | 0.73±0.01 |
| best fixed | 0.79 (eval_optimizer) |
| oracle per-task | 0.89 |
| selector | 0.71±0.03 |

## Tokens per task

### GSM8K

| pattern | gpt-oss-20b | ministral-8b | llama-3.1-8b |
|---|---|---|---|
| single | 398 | 528 | 324 |
| chain | 972 | 685 | 599 |
| debate | 1226 | 1839 | 1095 |
| eval_optimizer | 1019 | 803 | 876 |
| orchestrator | 1893 | 276848 | 11188 |
| blackboard | 1692 | 2087 | 1293 |

### MMLU

| pattern | gpt-oss-20b | ministral-8b | llama-3.1-8b |
|---|---|---|---|
| single | 849 | 1026 | 584 |
| chain | 1749 | 1797 | 991 |
| debate | 2892 | 4236 | 2291 |
| eval_optimizer | 2768 | 7946 | 2682 |
| orchestrator | 2679 | 65978 | 15626 |
| blackboard | 3138 | 5595 | 2590 |

### MathQA

| pattern | gpt-oss-20b |
|---|---|
| single | 870 |
| chain | 1856 |
| debate | 3253 |
| eval_optimizer | 3499 |
| orchestrator | 2183 |
| blackboard | 3178 |

### LogiQA

| pattern | gpt-oss-20b |
|---|---|
| single | 1481 |
| chain | 2682 |
| debate | 4104 |
| eval_optimizer | 6248 |
| orchestrator | 3444 |
| blackboard | 4952 |

## Per-task headroom — gpt-oss-20b (one executor across difficulty)

| benchmark | single | best fixed | oracle per-task | headroom |
|---|---|---|---|---|
| GSM8K | 0.94 | 0.95 | 0.98 | +3pp |
| MMLU | 0.89 | 0.89 | 0.95 | +6pp |
| LogiQA | 0.77 | 0.79 | 0.89 | +9pp |
| MathQA (capped) | 0.73 | 0.73 | 0.74 | +1pp |

_Selector single-run except LogiQA/gpt-oss-20b (3 runs); MathQA selector not run. Figures: benchmarks/figures/{headroom,pareto,selector}.png._
