"""Article figures from the recorded runs. Three plots, one message each:
headroom-vs-difficulty (the law), accuracy-vs-cost (single is Pareto), selector-vs-baselines.

    uv run --group examples --group bench python benchmarks/plots.py
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
from report import ORDER, OUT, load, metrics, stable_oracle

FIGS = Path(__file__).parent / "figures"
GPT_OSS = "openrouter:openai/gpt-oss-20b"
PATS = [p for p in ORDER if p != "router"]
LABELS = {"debate": "voting"}  # display only; recorded data keeps the original name

TEXT = {
    "en": {
        "suffix": "",
        "hr_title": "Per-task headroom grows as the task gets hard for the model\n(gpt-oss-20b, same model throughout)",
        "hr_x": "single-agent accuracy on the benchmark  (executor gets weaker →)",
        "hr_band": "per-task headroom",
        "hr_oracle": "oracle (per-task)",
        "hr_best": "best fixed pattern",
        "pp": "pp",
        "acc": "accuracy",
        "pa_title": "single (red) is on the cost/accuracy frontier (gpt-oss-20b)",
        "pa_x": "tokens / task, log scale (cheaper →)",
        "pa_frontier": "Pareto frontier",
        "pa_easy": "GSM8K (easy)",
        "pa_hard": "LogiQA (hard)",
        "se_title": "LogiQA / gpt-oss-20b: headroom exists, zero-shot selection misses it",
        "se_labels": ["single", "random", "selector", "oracle\n(per-task)"],
    },
    "ru": {
        "suffix": "_ru",
        "hr_title": "Запас на выбор под задачу растёт по мере усложнения бенчмарка\n(gpt-oss-20b, одна и та же модель)",
        "hr_x": "точность одиночного агента на бенчмарке  (модель слабеет →)",
        "hr_band": "запас (выбор на задачу)",
        "hr_oracle": "оракул (на задачу)",
        "hr_best": "лучший фиксированный паттерн",
        "pp": "пп",
        "acc": "точность",
        "pa_title": "single (красный) на границе «стоимость/точность» (gpt-oss-20b)",
        "pa_x": "токенов на задачу, лог. шкала (дешевле →)",
        "pa_frontier": "граница Парето",
        "pa_easy": "GSM8K (лёгкий)",
        "pa_hard": "LogiQA (трудный)",
        "se_title": "LogiQA / gpt-oss-20b: запас есть, zero-shot выбор его не берёт",
        "se_labels": [
            "single",
            "random\n(случайно)",
            "selector\n(селектор)",
            "оракул\n(на задачу)",
        ],
    },
}


def agg(bench: str, model: str) -> dict:
    ms = [
        metrics(r)
        for d in sorted(OUT.glob(f".out_{bench}_gpt4omini-*"))
        if (r := load(d, bench, model))
    ]
    if not ms:
        raise SystemExit(f"no records for {bench}/{model}")
    pats = [p for p in PATS if all(p in m["acc"] for m in ms)]
    acc = {p: sum(m["acc"][p] for m in ms) / len(ms) for p in pats}
    tok = {p: sum(m["tok"][p] for m in ms) / len(ms) for p in pats}
    return {
        "acc": acc,
        "tok": tok,
        "best_fixed": max(acc.values()),
        "oracle": stable_oracle(ms),
        "random": sum(m["random"] for m in ms) / len(ms),
    }


def fig_headroom(t: dict) -> None:
    # one executor (gpt-oss-20b) across benchmarks; gap widens as the task gets hard for it
    order = [("gsm8k", "GSM8K"), ("mmlu", "MMLU"), ("logiqa", "LogiQA")]
    rows = [(agg(b, GPT_OSS), name) for b, name in order]
    xs = [r["acc"]["single"] for r, _ in rows]
    best = [r["best_fixed"] for r, _ in rows]
    orac = [r["oracle"] for r, _ in rows]

    fig, ax = plt.subplots(figsize=(7, 4.5))
    ax.fill_between(xs, best, orac, color="tab:orange", alpha=0.15, label=t["hr_band"])
    ax.plot(xs, orac, "o-", color="tab:orange", label=t["hr_oracle"])
    ax.plot(xs, best, "s-", color="tab:blue", label=t["hr_best"])
    for (r, name), x, o in zip(rows, xs, orac):
        gap = round((r["oracle"] - r["best_fixed"]) * 100)
        # centred above the point; margins below give every label room to clear the frame
        ax.annotate(
            f"{name}  +{gap} {t['pp']}",
            (x, o),
            textcoords="offset points",
            xytext=(0, 9),
            ha="center",
            va="bottom",
        )
    pad = (max(xs) - min(xs)) * 0.12
    ax.set_xlim(max(xs) + pad, min(xs) - pad)  # inverted: weaker executor to the right
    ax.set_ylim(min(best) - 0.015, max(orac) + 0.03)
    ax.set_xlabel(t["hr_x"])
    ax.set_ylabel(t["acc"])
    ax.set_title(t["hr_title"])
    ax.legend()
    fig.tight_layout()
    fig.savefig(FIGS / f"headroom{t['suffix']}.png", dpi=150)
    plt.close(fig)


def _frontier(acc: dict, tok: dict, pats: list[str]) -> list[str]:
    # non-dominated set (minimize tokens, maximize accuracy): walk from the cheapest, keep a
    # point only if it beats every cheaper one on accuracy. Returned sorted by cost ascending.
    front: list[str] = []
    best = -1.0
    for p in sorted(pats, key=lambda p: tok[p]):
        if acc[p] > best:
            front.append(p)
            best = acc[p]
    return front


def fig_pareto(t: dict) -> None:
    # two panels: easy (converge) vs hard (spread). x inverted so cheaper is to the right and
    # the good corner is top-right; the frontier line traces the non-dominated points.
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.5), sharey=False)
    for ax, (bench, name) in zip(
        axes, [("gsm8k", t["pa_easy"]), ("logiqa", t["pa_hard"])]
    ):
        a = agg(bench, GPT_OSS)
        front = _frontier(a["acc"], a["tok"], list(a["acc"]))
        ax.plot(
            [a["tok"][p] for p in front],
            [a["acc"][p] for p in front],
            "-",
            color="tab:blue",
            alpha=0.45,
            zorder=2,
            label=t["pa_frontier"],
        )
        for p in a["acc"]:
            color = "tab:red" if p == "single" else "tab:gray"
            ax.scatter(a["tok"][p], a["acc"][p], s=70, color=color, zorder=3)
            ax.annotate(
                LABELS.get(p, p),
                (a["tok"][p], a["acc"][p]),
                textcoords="offset points",
                xytext=(6, 3),
                fontsize=9,
            )
        ax.set_xscale("log")
        ax.invert_xaxis()  # cheaper to the right
        ax.margins(x=0.18)  # room for the labels
        ax.set_xlabel(t["pa_x"])
        ax.set_ylabel(t["acc"])
        ax.set_title(name)
        ax.grid(True, alpha=0.3)
        ax.legend(loc="lower left", fontsize=9)
    fig.suptitle(t["pa_title"])
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    fig.savefig(FIGS / f"pareto{t['suffix']}.png", dpi=150)
    plt.close(fig)


def fig_selector(t: dict) -> None:
    # logiqa/gpt-oss: the column with the largest headroom; selector cannot reach it
    a = agg("logiqa", GPT_OSS)
    values = [a["acc"]["single"], a["random"], 0.71, a["oracle"]]
    colors = ["tab:red", "tab:gray", "tab:purple", "tab:orange"]
    fig, ax = plt.subplots(figsize=(6.5, 4.5))
    bars = ax.bar(t["se_labels"], values, color=colors)
    ax.bar_label(bars, fmt="%.2f", padding=3)
    ax.set_ylim(0.5, 1.0)
    ax.set_ylabel(t["acc"])
    ax.set_title(t["se_title"])
    fig.tight_layout()
    fig.savefig(FIGS / f"selector{t['suffix']}.png", dpi=150)
    plt.close(fig)


def main() -> None:
    FIGS.mkdir(exist_ok=True)
    for t in TEXT.values():
        fig_headroom(t)
        fig_pareto(t)
        fig_selector(t)
    print(f"wrote {len(list(FIGS.glob('*.png')))} figures to {FIGS}")


if __name__ == "__main__":
    main()
