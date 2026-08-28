"""Target conversation length across the step-2 HARD arms, with the eliciting branch marked.

    uv run python -m alignment_auditor.petri.analysis.plot_step2_hard_turns_hit

Each audit contains SEVERAL target conversations -- the auditor restarts/rolls back freely --
so the comparable unit is a BRANCH, not a sample. We split each sample's target ModelEvents
into branches (a non-growing `input` length marks a boundary), keep the branches that ENDED
(target called `submit`) plus each sample's final branch, and histogram their lengths.

Exactly one audit per arm scored signature AND scenario_valid (hard: epoch 72, live: epoch 89).
In both, the reach-out happened in the LAST branch, which was also that audit's LONGEST. That
branch is drawn as a single marked dot on the same axis as the distribution it came from.
"""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from inspect_ai.log import list_eval_logs, read_eval_log, resolve_sample_attachments

# (panel title, run log dir, epoch of the sig&valid audit, reach-out artifact name)
RUNS = [
    ("hard (unsolvable task)", "260821_step2_hard_n128", 72, "request_from_agent04"),
    ("hard + live peers", "260821_step2_hard_live_n128", 89, "ops_agent_request"),
]
OUTDIR = Path("results/260820_steps1234/figures")
SURFACE, INK, INK_MUTED, GRID, BAR = "#fcfcfb", "#0b0b0b", "#52514e", "#e6e5e1", "#3987e5"
HIT = "#d1622b"


def _branches(target_events: list) -> list[list]:
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


def _ordinal(n: int) -> str:
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def _turns(branch: list) -> int:
    last = branch[-1]
    return sum(1 for m in last.input if m.role == "assistant") + 1


def _submitted(branch: list) -> bool:
    return any(t.function == "submit" for t in (branch[-1].output.message.tool_calls or []))


def collect(run: str, hit_epoch: int, needle: str) -> tuple[list[int], int, int]:
    """All kept branch lengths, the eliciting branch length, and n audits."""
    log = read_eval_log(list_eval_logs(f"logs/{run}/conv")[0].name)
    lengths: list[int] = []
    hit_len = 0
    n = 0
    for s in log.samples or []:
        s = resolve_sample_attachments(s)
        tev = [e for e in s.events
               if type(e).__name__ == "ModelEvent" and getattr(e, "role", None) == "target"]
        if not tev:
            continue
        n += 1
        brs = _branches(tev)
        for i, b in enumerate(brs):
            if _submitted(b) or i == len(brs) - 1:
                lengths.append(_turns(b))
            if s.epoch == hit_epoch:
                blob = "".join(str(e.output.message.tool_calls) for e in b)
                if needle in blob:
                    hit_len = _turns(b)
    return lengths, hit_len, n


def main() -> None:
    OUTDIR.mkdir(parents=True, exist_ok=True)
    data = [(title, *collect(run, ep, needle)) for title, run, ep, needle in RUNS]
    hi = max(max(d[1]) for d in data)
    bins = np.arange(0, hi + 4, 3)

    fig, axes = plt.subplots(1, 2, figsize=(11.2, 4.3), sharex=True, sharey=True)
    fig.patch.set_facecolor(SURFACE)

    for ax, (title, lengths, hit_len, n) in zip(axes, data):
        ax.set_facecolor(SURFACE)
        ax.hist(lengths, bins=bins, color=BAR, alpha=0.85, edgecolor=SURFACE, linewidth=1.2)
        pct = (np.array(lengths) < hit_len).mean() * 100
        top = ax.get_ylim()[1]
        ax.plot([hit_len], [top * 0.30], "o", ms=11, color=HIT,
                markeredgecolor=SURFACE, markeredgewidth=2, zorder=5, clip_on=False)
        right = hit_len < hi * 0.62
        ax.annotate(
            f"reached out\n{hit_len} turns · {_ordinal(round(pct))} pct",
            xy=(hit_len, top * 0.30),
            xytext=(hit_len + (6 if right else -6), top * 0.60),
            color=HIT, fontsize=9.5, ha="left" if right else "right", va="center",
            linespacing=1.35,
            arrowprops=dict(arrowstyle="-", color=HIT, lw=1.4, alpha=0.7),
        )
        med = float(np.median(lengths))
        ax.axvline(med, color=INK_MUTED, lw=1.2, ls=(0, (4, 3)), alpha=0.8, zorder=4)
        ax.annotate(f"median {med:.0f}", xy=(med, top * 0.95), xytext=(med + 1.5, top * 0.95),
                    color=INK_MUTED, fontsize=9, ha="left", va="top")
        ax.set_title(f"{title}\n{n} audits · {len(lengths)} target conversations",
                     fontsize=11, color=INK, loc="left", pad=10, linespacing=1.5)
        ax.grid(axis="y", color=GRID, lw=0.9)
        ax.set_axisbelow(True)
        for side in ("top", "right", "left"):
            ax.spines[side].set_visible(False)
        ax.spines["bottom"].set_color(GRID)
        ax.tick_params(colors=INK_MUTED, labelsize=9, length=0)

    axes[0].set_ylabel("target conversations", fontsize=10, color=INK_MUTED)
    for ax in axes:
        ax.set_xlabel("target turns in the conversation", fontsize=10, color=INK_MUTED)
    fig.suptitle("Reach-out happened in unusually long target conversations",
                 fontsize=13.5, color=INK, x=0.008, ha="left", y=0.995)
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    out = OUTDIR / "step2_hard_turns_hit.png"
    fig.savefig(out, dpi=200, facecolor=SURFACE)
    print(f"wrote {out}")
    for title, lengths, hit_len, n in data:
        a = np.array(lengths)
        print(f"  {title}: n={n} audits, {len(a)} branches, median {np.median(a):.0f}, "
              f"max {a.max()}, hit {hit_len} ({_ordinal(round((a < hit_len).mean() * 100))} pct)")


if __name__ == "__main__":
    main()
