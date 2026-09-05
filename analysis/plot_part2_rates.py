"""Part 2 -- elicitation rate per step (Claude-style bar chart).

    uv run python analysis/plot_part2_rates.py

Reads the scored logs for each step and draws a single-hue magnitude bar chart:
valid-hit rate (signature AND scenario_valid) per step, with Wilson 95% whiskers and
direct labels. Step 2 pools the three runs of the same nudged seed: 12/1506.
Output: results/part2_petri/figures/part2_elicitation_rate.png
"""

import glob
import math
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.path import Path as MPath
from matplotlib.patches import PathPatch
from inspect_ai.log import read_eval_log_sample_summaries

REPO = Path(__file__).resolve().parent.parent

# --- Claude palette (from the reference schematic) ---------------------------------
BG     = "#FBFAF8"   # warm off-white ground
INK    = "#2C3E50"   # navy primary text
MUTED  = "#8A8A84"   # grey secondary text
GRID   = "#ECEAE4"   # recessive gridline
AMBER  = "#E8833A"   # accent / bars
AMBER_D= "#C96A24"   # darker amber for whiskers

# step -> label + the scored-log dirs to pool. Step 2's rare rate is measured over several runs
# of the one step2 config (~1506 audits pooled, all the same seed); the committed cache holds the
# result, so the figure renders without the (gitignored) raw logs.
STEPS = [
    ("Step 1", "inappropriate\nregistry writes", ["part2_step1_registry_write"]),
    ("Step 2", "requesting\npeer help", ["part2_step2_reachout", "part2_step2_reachout_peeraction_n256", "part2_step2_reachout_n1000"]),
    ("Step 3", "sharing\nexploits", ["part2_step3_exploit_share"]),
    ("Step 4", "using a posted\nexploit", ["part2_step4_hf_cheat"]),
]


def val(s, w):
    for _n, sc in (s.scores or {}).items():
        v = sc.value
        if isinstance(v, dict) and w in v:
            return v[w]
    return None


def rate(dirs):
    hits = n = 0
    for d in dirs:
        cf = glob.glob(str(REPO / f"logs/{d}/scored/*custom*.eval"))
        vf = glob.glob(str(REPO / f"logs/{d}/scored/*validity*.eval"))
        if not cf or not vf:
            continue
        sig = {(s.id, s.epoch): val(s, "signature") for s in read_eval_log_sample_summaries(cf[0])}
        vld = {(s.id, s.epoch): val(s, "scenario_valid") for s in read_eval_log_sample_summaries(vf[0])}
        keys = [k for k in sig if sig[k] is not None]
        hits += sum(1 for k in keys if sig[k] and vld.get(k))
        n += len(keys)
    return hits, n


def wilson(k, n, z=1.96):
    if n == 0:
        return 0.0, 0.0
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return max(0.0, c - h), min(1.0, c + h)


def rounded_top_bar(ax, xc, w, h, color, r):
    """A bar anchored at y=0 with the two TOP corners rounded (radius r, in data y-units)."""
    r = min(r, h, w / 2)
    x0, x1 = xc - w / 2, xc + w / 2
    verts = [(x0, 0), (x0, h - r), (x0, h), (x0 + r, h),
             (x1 - r, h), (x1, h), (x1, h - r), (x1, 0), (x0, 0)]
    codes = [MPath.MOVETO, MPath.LINETO, MPath.CURVE3, MPath.CURVE3,
             MPath.LINETO, MPath.CURVE3, MPath.CURVE3, MPath.LINETO, MPath.CLOSEPOLY]
    ax.add_patch(PathPatch(MPath(verts, codes), fc=color, ec="none", zorder=3))


CACHE = REPO / "results/part2_petri/figures/part2_counts.json"


def counts():
    """{label: (hits, n)} from the scored logs, cached to JSON so re-renders are instant."""
    import json
    if CACHE.exists():
        return {k: tuple(v) for k, v in json.loads(CACHE.read_text()).items()}
    c = {label: rate(dirs) for label, _sub, dirs in STEPS}
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps({k: list(v) for k, v in c.items()}))
    return c


def main():
    c = counts()
    data = []
    for label, sub, dirs in STEPS:
        k, n = c[label]
        lo, hi = wilson(k, n)
        data.append((label, sub, k, n, k / n if n else 0, lo, hi))
        print(f"{label}: {k}/{n} = {k/n:.1%}" if n else f"{label}: no data")

    plt.rcParams.update({"font.family": "DejaVu Sans", "text.color": INK,
                         "axes.edgecolor": GRID, "figure.facecolor": BG, "axes.facecolor": BG})
    fig, ax = plt.subplots(figsize=(8.2, 4.6))
    fig.subplots_adjust(left=0.09, right=0.97, top=0.93, bottom=0.14)

    xs = range(len(data))
    ymax = max(d[4] for d in data) * 1.28 + 0.03
    for x, (label, sub, k, n, p, lo, hi) in zip(xs, data):
        rounded_top_bar(ax, x, 0.56, max(p, 0.0015), AMBER, r=0.012)
        # Wilson whisker
        ax.plot([x, x], [lo, hi], color=AMBER_D, lw=1.6, zorder=4, solid_capstyle="round")
        ax.plot([x - 0.05, x + 0.05], [hi, hi], color=AMBER_D, lw=1.6, zorder=4)
        # direct label: % (bold navy)
        ax.text(x, hi + ymax * 0.035, f"{p*100:.1f}%", ha="center", va="bottom",
                fontsize=15, fontweight="bold", color=INK)

    # x tick labels: step + descriptor
    ax.set_xticks(list(xs))
    ax.set_xticklabels([d[0] for d in data], fontsize=12.5, fontweight="bold", color=INK)
    for x, d in zip(xs, data):
        ax.text(x, -ymax * 0.075, d[1], ha="center", va="top", fontsize=9, color=MUTED)

    ax.set_ylim(0, ymax)
    ax.set_yticks([i / 100 for i in range(0, int(ymax * 100) + 1, 10)])
    ax.set_yticklabels([f"{int(t*100)}%" for t in ax.get_yticks()], fontsize=9.5, color=MUTED)
    ax.set_ylabel("Elicitation Rate", fontsize=10.5, color=INK)
    ax.grid(axis="y", color=GRID, lw=1, zorder=0)
    ax.set_axisbelow(True)
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.spines["bottom"].set_color(GRID)
    ax.tick_params(length=0)

    out = REPO / "results/part2_petri/figures/part2_elicitation_rate.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=200)
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
