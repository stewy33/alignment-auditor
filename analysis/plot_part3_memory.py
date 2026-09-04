"""Part 3 vs Part 2 -- cost to first valid Step-2 hit: naive iid vs the Poor-Man's-RL loop.

    uv run python analysis/plot_part3_memory.py

Same axes as the Part-2 cost figure: x = compute cost (USD), y = P(>=1 valid Step-2
elicitation). Two arms:

  * iid (Part 2, naive)  -- the bare auditor, Step 2 pooled (2/509). Cost-to-first-hit is the
    geometric wait at the measured mean $/audit, so the closed-form CDF is 1-e^(-λX), shaded
    with a band from the Wilson interval on p. The "just sample more" baseline.
  * Poor-Man's-RL (Part 3) -- the reviewer-driven memory loop. 5 replicates, each with a real
    dollar cost to its first valid hit (cost_model.cost_to_first_hit: the whole hitting wave +
    the amortised reviewer spend). With only n=5 we FIT a log-normal (positive, right-skewed
    cost) by probability-plot regression -- the straight line through the 5 points at their
    (i-0.5)/n plotting positions -- and carry the uncertainty with a bootstrap band (resample
    the reps, refit). The 5 replicates are drawn as dots the fitted line passes through.

Two figures (results/part3_poor_mans_rl/figures/):
    part3_vs_part2_cost.png   the two cost-to-first-hit CDFs, each with an uncertainty band
    part3_cost_reduction.png  the same comparison as grouped bars on a linear $ axis, where the
                              ×saving reads as a height gap (point estimates; see the CDF for error)
"""

import json
import math
from pathlib import Path
from statistics import NormalDist

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from alignment_auditor.petri.cost_model import cost_to_first_hit, load_memory_run

REPO = Path(__file__).resolve().parent.parent
OUTDIR = REPO / "results/part3_poor_mans_rl/figures"
MEMORY_RUN = "part3_step2_memory"
PART2_CACHE = REPO / "results/part2_petri/figures/part2_cost_data.json"

# --- Claude palette ----------------------------------------------------------------------
BG    = "#FBFAF8"
INK   = "#2C3E50"
MUTED = "#8A8A84"
GRID  = "#ECEAE4"
AMBER = "#E8833A"   # Poor-Man's-RL (the hero)
AMBER_D = "#C96A24"
IID   = "#7E8A97"   # naive iid baseline (recessive slate)

RNG = np.random.default_rng(0)
BOOT = 2000
_erf = np.vectorize(math.erf)
_N = NormalDist()


def normal_cdf(x, mu, sigma):
    sigma = max(sigma, 1e-9)
    return 0.5 * (1.0 + _erf((np.log(x) - mu) / (sigma * math.sqrt(2))))


def plotting_pos(n):
    """Hazen plotting positions (i-0.5)/n: the y-heights at which the sorted sample points are
    expected to sit on a well-fitting CDF (so the fit can actually pass through them; i/n would
    put the top point at 1.0, wrongly implying certainty at the largest observed cost)."""
    return (np.arange(1, n + 1) - 0.5) / n


def lognormal_fit(vals):
    """Log-normal by probability-plot regression: least-squares of ln(cost) on Φ⁻¹((i-0.5)/n),
    i.e. the straight line drawn THROUGH the points in log-probit space. Returns (μ, σ) =
    (intercept, slope), so the fitted CDF interpolates the sample points by construction."""
    cs = np.sort(vals)
    z = np.array([_N.inv_cdf(p) for p in plotting_pos(len(cs))])
    A = np.vstack([np.ones(len(cs)), z]).T
    mu, sigma = np.linalg.lstsq(A, np.log(cs), rcond=None)[0]
    return float(mu), float(max(sigma, 1e-9))


def wilson(k, n, z=1.96):
    if n == 0:
        return 0.0, 0.0
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return max(0.0, c - h), min(1.0, c + h)


def iid_step2():
    """(k, n, c̄) for the Part-2 Step-2 iid arm, from the cost cache -- k valid hits in n
    audits at mean $/audit c̄. Uncertainty is the Wilson interval on p=k/n."""
    d = json.loads(PART2_CACHE.read_text())["Step 2"]
    costs = np.array(d["costs"], float)
    wins = np.array(d["wins"], bool)
    return int(wins.sum()), len(wins), float(costs.mean())


def rate_from(p, cbar):
    """Exponential rate λ = -ln(1-p)/c̄ of the iid cost-to-first-hit (0 if p or c̄ is 0)."""
    if p <= 0 or cbar <= 0:
        return 0.0
    return -math.log1p(-p) / cbar


def style(ax):
    ax.set_facecolor(BG)
    ax.grid(color=GRID, linewidth=1, zorder=0)
    ax.set_axisbelow(True)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(GRID)
    ax.tick_params(axis="both", labelsize=9, colors=MUTED, length=0)
    ax.set_ylim(-0.03, 1.03)
    ax.set_yticks([0, 0.25, 0.5, 0.75, 1.0])


def dollar_ticks(ax):
    ax.set_xscale("log", base=2)
    lo, hi = ax.get_xlim()
    ticks = [2.0 ** k for k in range(int(np.floor(np.log2(lo))), int(np.ceil(np.log2(hi))) + 1)]
    ax.set_xticks(ticks)
    ax.set_xticklabels([f"${t:g}" if t >= 1 else f"${t:.2f}" for t in ticks])


def draw_bars(lam, mu, sigma, out):
    """Grouped bars on a LINEAR $ axis: compute to reach each confidence level, iid vs the
    memory loop, with the ×saving over each pair. Linear (not log) so a 2.4x saving reads as a
    2.4x height gap -- the point the CDF's log-x axis hides.

    Point estimates only: the honest uncertainty (iid's Wilson band on p=2/509, memory's
    bootstrap) lives in the CDF figure -- on this linear $ axis the iid high-confidence band
    runs to ~$7k and would dwarf the bars, so it is deliberately left to the CDF."""
    confs = [0.50, 0.80, 0.90, 0.95]
    iid = [-math.log(1 - q) / lam for q in confs]
    mem = [math.exp(mu + sigma * _N.inv_cdf(q)) for q in confs]
    print("\ncost to reach confidence (iid vs memory):")
    for q, a, b in zip(confs, iid, mem):
        print(f"  {q:.0%}: iid ${a:,.0f}  RL ${b:,.0f}  ->  {a/b:.1f}x cheaper")

    fig, ax = plt.subplots(figsize=(8.2, 5.0))
    fig.patch.set_facecolor(BG)
    fig.subplots_adjust(left=0.11, right=0.97, top=0.93, bottom=0.17)
    ax.set_facecolor(BG)
    ax.grid(axis="y", color=GRID, linewidth=1, zorder=0)
    ax.set_axisbelow(True)

    x = np.arange(len(confs))
    w = 0.38
    ymax = max(iid) * 1.20
    ax.bar(x - w / 2, iid, w, color=IID, zorder=3, label="Part 2 · iid")
    ax.bar(x + w / 2, mem, w, color=AMBER, zorder=3, label="Part 3 · Poor-Man's-RL")
    for xi, v in zip(x - w / 2, iid):
        ax.text(xi, v + ymax * 0.012, f"${v:,.0f}", ha="center", va="bottom",
                fontsize=9, color=MUTED)
    for xi, v in zip(x + w / 2, mem):
        ax.text(xi, v + ymax * 0.012, f"${v:,.0f}", ha="center", va="bottom",
                fontsize=9, fontweight="bold", color=AMBER_D)
    for xi, vi, vm in zip(x, iid, mem):
        ax.text(xi, max(vi, vm) + ymax * 0.085, f"{vi/vm:.1f}× cheaper", ha="center",
                va="bottom", fontsize=11.5, fontweight="bold", color=INK)

    ax.set_ylim(0, ymax)
    ax.set_xticks(x)
    ax.set_xticklabels([f"{int(q*100)}%" for q in confs], fontsize=12.5, fontweight="bold",
                       color=INK)
    ax.set_xlabel("P(≥1 Step-2 elicitation)", fontsize=10.5, color=INK)
    fig.text(0.11, 0.035, "Point estimates; uncertainty shown in the cost-vs-probability figure.",
             fontsize=8, color=MUTED)
    yt = list(range(0, int(ymax) + 1, 500))
    ax.set_yticks(yt)
    ax.set_yticklabels([f"${t:,}" for t in yt], fontsize=9.5, color=MUTED)
    ax.set_ylabel("Compute Cost (USD)", fontsize=10.5, color=INK)
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.spines["bottom"].set_color(GRID)
    ax.tick_params(length=0)
    leg = ax.legend(loc="upper left", frameon=True, fontsize=9.5, labelcolor=INK,
                    handlelength=1.4, borderpad=0.7)
    leg.get_frame().set_facecolor(BG)
    leg.get_frame().set_edgecolor(GRID)
    leg.get_frame().set_linewidth(1)

    fig.savefig(out, dpi=200, facecolor=BG)
    plt.close(fig)
    print("wrote", out)


def main():
    OUTDIR.mkdir(parents=True, exist_ok=True)

    # --- Part 3 memory arm: dollar cost to first valid hit, per replicate ---
    records = load_memory_run(MEMORY_RUN)
    costs = np.array([c for c in cost_to_first_hit(records) if np.isfinite(c)], float)
    costs.sort()
    print(f"memory reps (n={len(costs)}): " + ", ".join(f"${c:,.0f}" for c in costs))
    print(f"  median ${np.median(costs):,.0f}  mean ${costs.mean():,.0f}")

    # --- Part 2 iid arm (rate + Wilson band on p = k/n) ---
    k, n, cbar = iid_step2()
    lam = rate_from(k / n, cbar)
    plo, phi = wilson(k, n)
    lam_lo, lam_hi = rate_from(plo, cbar), rate_from(phi, cbar)   # p_hi -> λ_hi -> cheaper
    print(f"iid Step 2: {k}/{n}  $/audit={cbar:.2f}  median ${math.log(2)/lam:,.0f}"
          f"  (95% p [{plo:.4f},{phi:.4f}])")

    xs = np.exp(np.linspace(np.log(4), np.log(2 ** 12), 400))

    fig, ax = plt.subplots(figsize=(8.6, 5.4))
    fig.patch.set_facecolor(BG)
    fig.subplots_adjust(left=0.10, right=0.97, top=0.95, bottom=0.13)
    style(ax)

    # iid baseline (recessive) + Wilson band from the uncertainty in p = k/n
    ax.fill_between(xs, 1.0 - np.exp(-lam_lo * xs), 1.0 - np.exp(-lam_hi * xs),
                    color=IID, alpha=0.15, linewidth=0, zorder=2)
    ax.plot(xs, 1.0 - np.exp(-lam * xs), "-", color=IID, linewidth=2.2, zorder=3,
            label="Part 2 · iid")

    # --- log-normal fit (through the points) + bootstrap band ---
    mu, sigma = lognormal_fit(costs)
    fit_y = normal_cdf(xs, mu, sigma)
    boot_params = np.array([lognormal_fit(RNG.choice(costs, size=len(costs), replace=True))
                            for _ in range(BOOT)])   # (BOOT, 2) of (μ, σ); reused by the bars
    boot = np.array([normal_cdf(xs, m, s) for m, s in boot_params])
    lo, hi = np.percentile(boot, [5, 95], axis=0)
    ax.fill_between(xs, lo, hi, color=AMBER, alpha=0.16, linewidth=0, zorder=4)
    ax.plot(xs, fit_y, "-", color=AMBER, linewidth=3.0, zorder=6,
            label="Part 3 · Poor-Man's-RL (log-normal fit)")
    # the 5 replicates at their (i-0.5)/n plotting positions -- the points the line interpolates
    pp = plotting_pos(len(costs))
    ax.scatter(costs, pp, s=44, color=AMBER_D, edgecolors=BG, linewidths=1.2, zorder=7,
               label="_nolegend_")

    med_mem = math.exp(mu)
    print(f"log-normal fit: median ${med_mem:,.0f}  (μ={mu:.2f}, σ={sigma:.2f})")

    dollar_ticks(ax)
    ax.set_xlabel("Compute Cost (USD)", fontsize=11, color=INK)
    ax.set_ylabel("P(≥1 Step-2 elicitation)", fontsize=11, color=INK)
    leg = ax.legend(loc="center left", bbox_to_anchor=(0.05, 0.72), frameon=True, fontsize=9.5,
                    labelcolor=INK, handlelength=1.6, borderpad=0.8, labelspacing=0.6)
    leg.get_frame().set_facecolor(BG)
    leg.get_frame().set_edgecolor(GRID)
    leg.get_frame().set_linewidth(1)

    out = OUTDIR / "part3_vs_part2_cost.png"
    fig.savefig(out, dpi=200, facecolor=BG)
    plt.close(fig)
    print("wrote", out)

    # second figure: the cost reduction, made obvious on a linear $ axis
    draw_bars(lam, mu, sigma, OUTDIR / "part3_cost_reduction.png")


if __name__ == "__main__":
    main()
