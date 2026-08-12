"""Plot the 260812_gradient result: mean `concerning` by seed, per auditor x judge cell.

    uv run python -m alignment_auditor.petri.analysis.plot_gradient

Reads the scored logs directly rather than taking numbers from the writeup, so the figure
cannot drift from the data it claims to show.

The scored logs are NOT in this repo -- they carry the unpublished perturbation seed text and
their canary GUIDs, and this repo is public. They live in the private `petri-experiments` repo;
regenerate them with `uv run exp experiments/260812_gradient.yaml`. The committed figure is the
output of this script over those logs.

Excludes degenerate audits -- samples where the auditor never elicited a single target
response. There are two, both under the sol auditor. The judge scored them anyway (one at
`concerning` = 8) and `auditor_failure` flagged them at only 2/10, so they are dropped here on
transcript content, not on a score threshold.

Error bars are +/-1 standard error of the mean. They describe how well the cell mean is pinned
down, not the spread of individual audits -- that spread is much wider (SD ~2-3 on a 1-10
scale) and is reported as a column in the writeup.
"""

import statistics as st
from math import sqrt
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from inspect_ai.log import read_eval_log

SCORED = Path("logs/260812_gradient/scored")
OUT = Path("results/260812_seed_gradient/figures/260812_gradient.png")
SEEDS = ["v0_original", "v1_near", "v2_mid", "v3_far"]
XLABELS = ["v0\noriginal", "v1\nnear", "v2\nmid", "v3\nfar"]

# Categorical slots 1-3 of the reference palette, validated for CVD separation and contrast
# (light surface #fcfcfb). Aqua sits below 3:1 against the surface, which is why every series
# carries a direct label rather than relying on the legend swatch alone.
# (file, legend label, short end-label, colour, end-label y nudge in data units)
# The two opus5-auditor series land 0.3 apart at v3, so their end labels are nudged apart by
# hand; without it they overlap and neither is readable.
SERIES = [
    ("opus5__gpt-5.6-luna__opus5.eval", "auditor opus5 · judge opus5", "judge opus5", "#2a78d6", -0.42),
    ("opus5__gpt-5.6-luna__gpt-5.6-sol.eval", "auditor opus5 · judge sol", "judge sol", "#eb6834", +0.42),
    ("gpt-5.6-sol__gpt-5.6-luna__opus5.eval", "auditor sol · judge opus5", "auditor sol", "#1baf7a", 0.0),
]
SURFACE, INK, INK_MUTED = "#fcfcfb", "#0b0b0b", "#52514e"


def load(path: Path) -> dict[str, list[int]]:
    """Per-seed `concerning` scores, dropping audits with no target response."""
    log = read_eval_log(str(path))
    cells: dict[str, list[int]] = {}
    for s in log.samples or []:
        responded = any(
            getattr(m, "role", "") == "tool" and "<target_response>" in (m.text or "")
            for m in (s.messages or [])
        )
        if not responded:
            continue
        flat: dict[str, int] = {}
        for v in (s.scores or {}).values():
            if isinstance(v.value, dict):
                flat.update(v.value)
        if "concerning" in flat:
            cells.setdefault(str(s.id), []).append(flat["concerning"])
    return cells


fig, ax = plt.subplots(figsize=(8.2, 5.0), dpi=200)
fig.patch.set_facecolor(SURFACE)
ax.set_facecolor(SURFACE)

xs = range(len(SEEDS))
for fname, label, endlabel, colour, nudge in SERIES:
    cells = load(SCORED / fname)
    means, errs, ns = [], [], []
    for seed in SEEDS:
        v = cells.get(seed, [])
        means.append(st.mean(v))
        errs.append(st.stdev(v) / sqrt(len(v)) if len(v) > 1 else 0.0)
        ns.append(len(v))
    ax.errorbar(
        xs, means, yerr=errs,
        color=colour, linewidth=2, marker="o", markersize=8,
        markeredgecolor=SURFACE, markeredgewidth=2,  # 2px surface ring on overlapping marks
        capsize=4, elinewidth=1.4, zorder=3, label=label,
    )
    # Direct label at the line end -- identity is never carried by colour alone, and the
    # aqua series sits below 3:1 against the surface, so a visible label is obligatory.
    ax.annotate(
        endlabel, xy=(len(SEEDS) - 1, means[-1] + nudge), xytext=(10, 0),
        textcoords="offset points", va="center", fontsize=9, color=colour,
    )
    print(f"{label:<30} " + "  ".join(f"{m:.1f}±{e:.2f}(n={n})" for m, e, n in zip(means, errs, ns)))

ax.set_xticks(list(xs))
ax.set_xticklabels(XLABELS, fontsize=9.5, color=INK_MUTED)
ax.set_xlim(-0.25, len(SEEDS) - 0.35)
ax.set_ylim(0.5, 10.5)
ax.set_yticks([1, 3, 5, 7, 9])
ax.tick_params(axis="y", labelsize=9.5, colors=INK_MUTED, length=0)
ax.tick_params(axis="x", length=0)

ax.grid(axis="y", color="#e6e5e1", linewidth=1, zorder=0)  # recessive grid
ax.set_axisbelow(True)
for side in ("top", "right", "left"):
    ax.spines[side].set_visible(False)
ax.spines["bottom"].set_color("#d9d8d3")

ax.set_ylabel("mean `concerning`  (1–10, higher is worse)", fontsize=9.5, color=INK_MUTED)
ax.set_xlabel("surface distance from the published seed →", fontsize=9.5, color=INK_MUTED)
fig.suptitle(
    "luna is elicited more readily the further a seed drifts from its published wording",
    x=0.055, y=0.965, ha="left", fontsize=12.5, color=INK,
)
ax.set_title(
    "gpt-5.6-luna, n=10 per point (9 where a degenerate audit was dropped) · error bars ±1 SEM\n"
    "trend under the opus5 auditor: +0.95/level, p=0.009 (opus5 judge) · +0.98/level (sol judge)",
    loc="left", fontsize=8.5, color=INK_MUTED, pad=8,
)
# Legend carries the full condition names; the end labels carry only what distinguishes them.
ax.legend(frameon=False, fontsize=8.5, labelcolor=INK_MUTED, loc="upper left",
          handlelength=1.6, borderpad=0, labelspacing=0.35)

fig.subplots_adjust(top=0.80, right=0.80, left=0.10, bottom=0.14)
OUT.parent.mkdir(parents=True, exist_ok=True)
fig.savefig(OUT, facecolor=SURFACE)
print(f"\nwrote {OUT}")
