"""Histogram of TARGET conversation length, one panel per step-2 arm.

    uv run python -m alignment_auditor.petri.analysis.plot_step2_turns

A turn is one target model call. The auditor restarts (`restart_conversation`) and rolls back
(`rollback_conversation`) freely, so a single audit contains SEVERAL target conversations --
median 4 in the rubric arm. Each of those is its own conversation with the target, so we

  1. split the sample's target ModelEvents into branches (a restart/rollback truncates the
     message history, so a non-growing `input` length is a branch boundary);
  2. keep the branches that ENDED -- the target called `submit` -- plus the sample's final
     branch, whether or not it got to submit (862 of 1053 branches here);
  3. average those branch lengths within the sample;

and plot the distribution of that per-sample mean across audits. A branch's length is the
assistant messages in its last target call's `input`, plus that call's own output.

`max_turns: 60` caps the AUDITOR loop, not the target, and no branch comes near it, so the cap
is not drawn.
"""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from inspect_ai.log import list_eval_logs, read_eval_log, resolve_sample_attachments

# (panel title, run log dir)
RUNS = [
    ("rubric (solvable)", "260819_step2_reachout_rubric_n256"),
    ("hard (unsolvable)", "260821_step2_hard_n128"),
    ("hard + live peers", "260821_step2_hard_live_n128"),
]
OUTDIR = Path("results/260820_steps1234/figures")
SURFACE, INK, INK_MUTED, GRID, BAR = "#fcfcfb", "#0b0b0b", "#52514e", "#e6e5e1", "#3987e5"


def _branches(target_events: list) -> list[list]:
    """Split target model calls into conversation branches at restarts/rollbacks."""
    out: list[list] = []
    cur: list = []
    prev = None
    for e in target_events:
        if prev is not None and len(e.input) <= prev:
            out.append(cur)
            cur = []
        cur.append(e)
        prev = len(e.input)
    if cur:
        out.append(cur)
    return out


def per_sample_mean_turns(run: str) -> tuple[list[float], dict]:
    log = read_eval_log(list_eval_logs(f"logs/{run}/conv")[0].name)
    means, stats = [], {"branches": 0, "kept": 0, "samples": 0}
    for s in log.samples or []:
        s = resolve_sample_attachments(s)
        tev = [e for e in s.events
               if type(e).__name__ == "ModelEvent" and getattr(e, "role", None) == "target"]
        if not tev:
            continue
        brs = _branches(tev)
        kept = []
        for i, b in enumerate(brs):
            last = b[-1]
            submitted = any(t.function == "submit" for t in (last.output.message.tool_calls or []))
            if submitted or i == len(brs) - 1:
                kept.append(sum(1 for m in last.input if m.role == "assistant") + 1)
        stats["branches"] += len(brs)
        stats["kept"] += len(kept)
        stats["samples"] += 1
        means.append(float(np.mean(kept)))
    return means, stats


def main() -> None:
    OUTDIR.mkdir(parents=True, exist_ok=True)
    data = {title: per_sample_mean_turns(run) for title, run in RUNS}
    hi = max(max(m) for m, _ in data.values())

    fig, axes = plt.subplots(len(RUNS), 1, figsize=(9, 3.0 * len(RUNS)), sharex=True)
    fig.patch.set_facecolor(SURFACE)
    for ax, (title, _) in zip(axes, RUNS):
        means, stats = data[title]
        n = len(means)
        med, mean = np.median(means), np.mean(means)
        print(f"{title:20} n={n:4} samples  {stats['branches']:5} branches "
              f"({stats['branches']/n:.1f}/sample, {stats['kept']} kept)  "
              f"median={med:.1f} mean={mean:.1f} "
              f"IQR={np.percentile(means,25):.1f}-{np.percentile(means,75):.1f} "
              f"p90={np.percentile(means,90):.1f} max={max(means):.1f}")
        ax.set_facecolor(SURFACE)
        # integers are bin CENTRES: many audits have a whole-number mean, and integer bin edges
        # split that mass arbitrarily into a comb.
        ax.hist(means, bins=np.arange(0.5, hi + 2, 1), color=BAR, zorder=3,
                edgecolor=SURFACE, linewidth=0.6)
        ax.grid(axis="y", color=GRID, linewidth=1, zorder=0)
        ax.set_axisbelow(True)
        for side in ("top", "right", "left"):
            ax.spines[side].set_visible(False)
        ax.spines["bottom"].set_color("#d9d8d3")
        ax.tick_params(axis="both", labelsize=9, colors=INK_MUTED, length=0)
        ax.set_xlim(0, hi + 2)
        ax.set_ylabel("audits", fontsize=10, color=INK)
        ax.set_title(f"{title} — n={n} audits, median {med:.1f}, mean {mean:.1f}",
                     fontsize=11, color=INK, loc="left")
    axes[-1].set_xlabel("mean target turns per conversation (within an audit)", fontsize=10,
                        color=INK)

    path = OUTDIR / "step2_target_turns_by_arm.png"
    fig.tight_layout()
    fig.savefig(path, dpi=200, facecolor=SURFACE)
    print("wrote", path)


if __name__ == "__main__":
    main()
