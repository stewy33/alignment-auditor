"""Grouped-bar elicitation plot across the incident's four steps -- three panels.

Step 2 is the 260821 IMPOSSIBLE-TASK arm (`step2_reachout_hard`), now the default step-2 seed:
the earlier solvable-task arm returned 0/255 signature because the targets were never actually
stuck. The hard arm holds validity (0.93) while finally landing the behaviour.

    uv run python -m alignment_auditor.petri.analysis.plot_steps_1234

Successor to plot_steps_123.py, which covered steps 1-3 only. Same visual grammar, one more
step, and stripped of the title/key furniture.

  1. Behavior              raw rung thresholds (>=1, >=2, >=3), over all sampled audits
  2. Scenario validity     fraction of audits the auditor built as a FAIR TEST
  3. Behavior + validity   the rung thresholds, counting only audits that were ALSO valid

Steps 1 and 4 ran under `stop_at_successful_n`. That was assumed to bias their rates upward via
a truncated denominator -- it does NOT, materially: analysis/stopping_bias.py simulates the exact
rule and finds E[r/N] - p = +0.002 (step 1) and +0.005 (step 4), an order of magnitude below their
confidence intervals. Audits are launched blind to outcome and the up-to-(max_parallel-1) in
flight when the Kth success lands are kept, so almost the whole sample is a clean iid draw. Those
steps are therefore plotted as ordinary bars; their small n shows up honestly as wide error bars.
"""

from math import sqrt
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from .cost_model import load_run

OUTDIR = Path("results/260821_steps1234/figures")

# (panel label, run log dir, early_stopped)
STEPS = [
    ("Step 1", "260814_ladder_glm52_L0", True),
    ("Step 2", "260821_step2_hard_n128", False),
    ("Step 3", "260819_step3_exploit_share_n256", False),
    ("Step 4", "260819_rung4_hf_cheat_rubsub_n128", True),
]
RUNGS = [
    (1, "explored beyond task (rung ≥1)", "#86b6ef"),
    (2, "attempted circumvention / took peer work (rung ≥2)", "#3987e5"),
    (3, "signature behaviour (rung ≥3)", "#184f95"),
]
VALID_COLOUR = "#2a78d6"
SURFACE, INK, INK_MUTED, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e6e5e1"


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return 0.0, 0.0
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return max(0.0, c - h), min(1.0, c + h)


def style(ax) -> None:
    ax.set_facecolor(SURFACE)
    ax.grid(axis="y", color=GRID, linewidth=1, zorder=0)
    ax.set_axisbelow(True)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color("#d9d8d3")
    ax.tick_params(axis="both", labelsize=9, colors=INK_MUTED, length=0)


def hatch_for(name: str) -> str | None:
    """No hatching: early stopping does not materially bias these rates (see stopping_bias.py)."""
    return None


def grouped_rungs(ax, data, gate_valid: bool) -> None:
    xs = list(range(len(STEPS)))
    width = 0.26
    for j, (thr, lab, colour) in enumerate(RUNGS):
        offs = (j - 1) * width
        heights, los, his = [], [], []
        for name, _, _ in STEPS:
            ss = [s for s in data[name] if "level" in s]
            n = len(ss)
            if gate_valid:
                k = sum(1 for s in ss if s["level"] >= thr and s.get("scenario_valid") == 1)
            else:
                k = sum(1 for s in ss if s["level"] >= thr)
            p = k / n if n else 0.0
            lo, hi = wilson(k, n)
            heights.append(p), los.append(p - lo), his.append(hi - p)
        px = [x + offs for x in xs]
        ax.bar(px, heights, width, label=lab, color=colour, zorder=3,
               hatch=[hatch_for(n) for n, _, _ in STEPS], edgecolor=SURFACE)
        ax.errorbar(px, heights, yerr=[los, his], fmt="none", ecolor="#9a9a97",
                    elinewidth=1.1, capsize=2.5, zorder=4)
        if thr == 3:
            for x, h in zip(px, heights):
                ax.text(x, h + 0.02, f"{h:.2f}", ha="center", va="bottom", fontsize=9, color=INK)
    ax.set_xticks(xs)
    ax.set_xticklabels([n for n, _, _ in STEPS], fontsize=10, color=INK)


def main() -> None:
    OUTDIR.mkdir(parents=True, exist_ok=True)
    data = {name: load_run(run) for name, run, _ in STEPS}

    print(f"{'step':8} {'n':>5} {'>=1':>6} {'>=2':>6} {'>=3':>6} {'valid':>6} {'>=3&valid':>10}")
    for name, _, stopped in STEPS:
        ss = [s for s in data[name] if "level" in s]
        n = len(ss) or 1
        row = [sum(1 for s in ss if s["level"] >= t) / n for t in (1, 2, 3)]
        vs = [s for s in data[name] if "scenario_valid" in s]
        v = sum(s["scenario_valid"] for s in vs) / (len(vs) or 1)
        j = sum(1 for s in ss if s["level"] >= 3 and s.get("scenario_valid") == 1) / n
        flag = "  (early-stopped; simulated bias <=0.005, see stopping_bias.py)" if stopped else ""
        print(f"{name:8} {len(ss):5} {row[0]:6.3f} {row[1]:6.3f} {row[2]:6.3f} {v:6.3f} {j:10.3f}{flag}")

    fig, axes = plt.subplots(1, 3, figsize=(15, 5), sharey=True)
    fig.patch.set_facecolor(SURFACE)
    for ax in axes:
        style(ax)
    axes[0].set_ylim(0, 1.0)
    axes[0].set_ylabel("rate", fontsize=10, color=INK_MUTED)

    grouped_rungs(axes[0], data, gate_valid=False)
    axes[0].set_title("Behavior", fontsize=12, color=INK, loc="left", pad=8)
    axes[0].legend(loc="upper right", frameon=False, fontsize=8)

    xs = list(range(len(STEPS)))
    vh, vlo, vhi = [], [], []
    for name, _, _ in STEPS:
        ss = [s for s in data[name] if "scenario_valid" in s]
        n, k = len(ss), sum(s["scenario_valid"] for s in ss)
        p = k / n if n else 0.0
        lo, hi = wilson(k, n)
        vh.append(p), vlo.append(p - lo), vhi.append(hi - p)
    axes[1].bar(xs, vh, 0.5, color=VALID_COLOUR, zorder=3,
                hatch=[hatch_for(n) for n, _, _ in STEPS], edgecolor=SURFACE)
    axes[1].errorbar(xs, vh, yerr=[vlo, vhi], fmt="none", ecolor="#9a9a97",
                     elinewidth=1.1, capsize=2.5, zorder=4)
    for x, h in zip(xs, vh):
        axes[1].text(x, h + 0.02, f"{h:.2f}", ha="center", va="bottom", fontsize=9, color=INK)
    axes[1].set_xticks(xs)
    axes[1].set_xticklabels([n for n, _, _ in STEPS], fontsize=10, color=INK)
    axes[1].set_title("Scenario validity", fontsize=12, color=INK, loc="left", pad=8)

    grouped_rungs(axes[2], data, gate_valid=True)
    axes[2].set_title("Behavior ∩ valid scenario", fontsize=12, color=INK, loc="left", pad=8)

    fig.tight_layout()
    out = OUTDIR / "260821_steps1234.png"
    fig.savefig(out, dpi=150, facecolor=SURFACE)
    print("wrote", out)


if __name__ == "__main__":
    main()
