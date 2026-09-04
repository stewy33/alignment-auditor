"""Part 2 -- P(>=1 elicitation) vs compute cost, all four steps + the whole incident, on one
chart (Claude-style).

    uv run python analysis/plot_part2_cost.py

For each step we have N sampled audits, each with a measured dollar cost and a binary
outcome (signature AND scenario_valid -- the same "valid hit" the rate figure counts).

The curves are closed-form -- no Monte Carlo. Keep auditing a step until the first valid hit:
the number of audits is Geometric(p) with p = the measured valid-hit rate, so the dollar cost
(at the measured mean c̄ per audit) is a geometric wait, whose smooth CDF is

    P(cost <= X) = 1 - (1 - p)^(X / c̄)   =   1 - e^(-λX),   λ = -ln(1 - p) / c̄

i.e. each step's cost-to-first-hit is Exponential(λ) (the continuous limit of the geometric).
The WHOLE INCIDENT is "run every step until it lands": total cost = the SUM of the four
independent exponentials, which is a HYPOEXPONENTIAL, and it too has a closed-form CDF

    P(sum <= X) = 1 - Σ_i A_i e^(-λ_i X),   A_i = Π_{j≠i} λ_j / (λ_j - λ_i)

giving P(all four behaviours elicited) vs total compute. Because the sum is >= any one step's
cost, the incident CDF is <= each step's at every budget by construction (recreating everything
requires Step 2, so it can never be more likely than eliciting Step 2 alone). Both forms are
exact and reproduce the measured medians (step median = ln2 / λ = c̄·ln2 / -ln(1-p)). Each
curve is shaded with the band from the Wilson interval on its measured p.

Output: results/part2_petri/figures/part2_cost_ci.png

COST comes straight from the scored logs (the local runs have no conv/ dir): each scored
log is a copy of the rollout, so the glm auditor+target `model_usage` rides along, and the
Opus judge's real per-sample spend is in each score's `judge_usage` metadata. Rollout is
taken once (from the custom log); judge cost sums the two judges the metric depends on
(custom + validity). See cost_model.py for the pricing and the no-double-count rationale.
"""

import glob
import math
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from inspect_ai.log import read_eval_log_sample_summaries

from alignment_auditor.petri.cost_model import reviewer_usage_cost, usage_cost

REPO = Path(__file__).resolve().parent.parent
OUTDIR = REPO / "results/part2_petri/figures"

# --- Claude palette (matches part2_elicitation_rate.png) ---------------------------------
BG    = "#FBFAF8"   # warm off-white ground
INK   = "#2C3E50"   # navy primary text
MUTED = "#8A8A84"   # grey secondary text
GRID  = "#ECEAE4"   # recessive gridline
# Four distinct categorical hues for the steps (dataviz skill's validated order: blue,
# orange, aqua, magenta -- passes CVD + normal-vision gates; identity also in the legend).
COLORS = ["#2a78d6", "#eb6834", "#1baf7a", "#e87ba4"]
INCIDENT = "#2C3E50"   # the whole-incident aggregate: dark navy, thick + dashed (an emphasis
                       # line, not a 5th category -- it tracks Step 2, styled to stand apart)

# step -> label + the scored-log dirs to pool (Step 2 pools the three nudged-seed runs, as the
# rate figure does: ~1506 audits total)
STEPS = [
    ("Step 1", "inappropriate registry writes", ["part2_step1_registry_write"]),
    ("Step 2", "requesting peer help", ["part2_step2_reachout", "part2_step2_reachout_peeraction_n256", "part2_step2_reachout_n1000"]),
    ("Step 3", "sharing exploits", ["part2_step3_exploit_share"]),
    ("Step 4", "using a posted exploit", ["part2_step4_hf_cheat"]),
]


def _val(sample, want):
    for _n, sc in (sample.scores or {}).items():
        v = sc.value
        if isinstance(v, dict) and want in v:
            return v[want]
    return None


def _judge_cost(sample):
    for sc in (sample.scores or {}).values():
        u = (sc.metadata or {}).get("judge_usage")
        if u and u.get("model"):
            return reviewer_usage_cost(u)
    return 0.0


def load_step(dirs):
    """(costs, wins) per audit, pooled over `dirs`. cost = glm rollout + custom + validity
    judge; win = signature AND scenario_valid.

    Reads the lightweight per-sample SUMMARIES (model_usage + scores + score metadata), not the
    full transcripts -- ~0.2s/file vs minutes for read_eval_log, and everything the cost/outcome
    needs lives in the summary."""
    costs, wins = [], []
    for d in dirs:
        cf = glob.glob(str(REPO / f"logs/{d}/scored/*custom*.eval"))
        vf = glob.glob(str(REPO / f"logs/{d}/scored/*validity*.eval"))
        if not cf or not vf:
            print(f"!! {d}: missing custom/validity scored log")
            continue
        # rollout cost + strict signature from the custom log (rollout taken here only)
        roll, sig, jc = {}, {}, {}
        for s in read_eval_log_sample_summaries(cf[0]):
            k = (s.id, s.epoch)
            roll[k] = sum(usage_cost(m, u) for m, u in (s.model_usage or {}).items())
            sig[k] = _val(s, "signature")
            jc[k] = _judge_cost(s)
        # scenario_valid + its judge cost from the validity log
        vld, jv = {}, {}
        for s in read_eval_log_sample_summaries(vf[0]):
            k = (s.id, s.epoch)
            vld[k] = _val(s, "scenario_valid")
            jv[k] = _judge_cost(s)
        for k in roll:
            if sig[k] is None or vld.get(k) is None:
                continue
            costs.append(roll[k] + jc.get(k, 0.0) + jv.get(k, 0.0))
            wins.append(bool(sig[k]) and bool(vld[k]))
    return np.array(costs, dtype=float), np.array(wins, dtype=bool)


DATA_CACHE = OUTDIR / "part2_cost_data.json"


def load_all():
    """[(costs, wins)] per step, cached to JSON so re-renders are instant."""
    import json
    if DATA_CACHE.exists():
        d = json.loads(DATA_CACHE.read_text())
        return [(np.array(d[l]["costs"], dtype=float), np.array(d[l]["wins"], dtype=bool))
                for l, _s, _dirs in STEPS]
    loaded = [load_step(dirs) for _l, _s, dirs in STEPS]
    DATA_CACHE.parent.mkdir(parents=True, exist_ok=True)
    DATA_CACHE.write_text(json.dumps(
        {l: {"costs": c.tolist(), "wins": w.tolist()}
         for (l, _s, _dirs), (c, w) in zip(STEPS, loaded)}))
    return loaded


def rate_from(p, cbar):
    """Exponential rate λ = -ln(1-p)/c̄ of a step's cost-to-first-hit (0 if p or c̄ is 0)."""
    if p <= 0 or cbar <= 0:
        return 0.0
    return -math.log1p(-p) / cbar


def step_rate(costs, wins):
    """λ from a step's measured valid-hit rate p and mean $/audit c̄."""
    return rate_from(float(wins.mean()), float(costs.mean()))


def wilson(k, n, z=1.96):
    """Wilson score interval (p_lo, p_hi) for k successes in n trials."""
    if n == 0:
        return 0.0, 0.0
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return max(0.0, c - h), min(1.0, c + h)


def step_cdf(lam, xs):
    """P(cost <= X) for one step: 1 - e^(-λX) (=0 everywhere if λ=0, a never-hitting step)."""
    return 1.0 - np.exp(-lam * xs)


def incident_cdf(lams, xs):
    """P(total <= X) for the sum of independent Exponential(λ_i): the hypoexponential CDF
    1 - Σ_i A_i e^(-λ_i X), A_i = Π_{j≠i} λ_j/(λ_j-λ_i). Requires distinct, positive λ."""
    lams = np.asarray(lams, dtype=float)
    A = np.array([np.prod([lams[j] / (lams[j] - lams[i])
                           for j in range(len(lams)) if j != i]) for i in range(len(lams))])
    return 1.0 - (A[:, None] * np.exp(-lams[:, None] * xs[None, :])).sum(axis=0)


def quantile(cdf_vals, xs, q):
    """Smallest X on the grid whose CDF >= q (the budget at which P >= q)."""
    idx = np.searchsorted(cdf_vals, q)
    return xs[min(idx, len(xs) - 1)]


def style(ax):
    ax.set_facecolor(BG)
    ax.grid(color=GRID, linewidth=1, zorder=0)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(GRID)
    ax.tick_params(axis="both", labelsize=9, colors=MUTED, length=0)
    ax.set_ylim(-0.03, 1.03)
    ax.set_yticks([0, 0.25, 0.5, 0.75, 1.0])


def dollar_ticks(ax, lo, hi):
    ax.set_xscale("log", base=2)
    ax.set_xlim(lo, hi)   # tight to the data -- no empty margin
    ticks = [2.0 ** k for k in range(int(np.ceil(np.log2(lo))), int(np.floor(np.log2(hi))) + 1)]
    ax.set_xticks(ticks)
    ax.set_xticklabels([f"${t:g}" if t >= 1 else f"${t:.2f}" for t in ticks])


def draw(loaded, lams, xs, out):
    """Render the figure: each step's closed-form cost CDF + the whole-incident hypoexponential,
    each shaded with the band from the Wilson interval on its measured p (the dominant sampling
    error; c̄ held fixed). The incident CDF is monotone increasing in every λ, so its band
    envelope is exactly the all-λ_lo (slowest) and all-λ_hi (fastest) corners -- no MC."""
    fig, ax = plt.subplots(figsize=(8.6, 5.4))
    fig.patch.set_facecolor(BG)
    fig.subplots_adjust(left=0.10, right=0.97, top=0.95, bottom=0.13)
    style(ax)

    handles = []
    for (label, sub, _dirs), (costs, wins), lam, col in zip(STEPS, loaded, lams, COLORS):
        line, = ax.plot(xs, step_cdf(lam, xs), "-", color=col, linewidth=2.2, zorder=3,
                        label=f"{label} · {sub}")
        plo, phi = wilson(int(wins.sum()), len(wins))
        cbar = float(costs.mean())
        ax.fill_between(xs, step_cdf(rate_from(plo, cbar), xs), step_cdf(rate_from(phi, cbar), xs),
                        color=col, alpha=0.15, linewidth=0, zorder=2)
        handles.append(line)

    inc, = ax.plot(xs, incident_cdf(lams, xs), "--", color=INCIDENT, linewidth=3.0, zorder=6,
                   label="Whole incident (all 4)")
    lo = [rate_from(wilson(int(w.sum()), len(w))[0], float(c.mean())) for c, w in loaded]
    hi = [rate_from(wilson(int(w.sum()), len(w))[1], float(c.mean())) for c, w in loaded]
    ax.fill_between(xs, incident_cdf(lo, xs), incident_cdf(hi, xs),
                    color=INCIDENT, alpha=0.13, linewidth=0, zorder=5)
    handles.append(inc)

    dollar_ticks(ax, xs[0], xs[-1])
    ax.set_xlabel("Compute Cost (USD)", fontsize=11, color=INK)
    ax.set_ylabel("P(≥1 elicitation)", fontsize=11, color=INK)
    leg = ax.legend(handles=handles, loc="center", bbox_to_anchor=(0.37, 0.63),
                    frameon=True, fontsize=9, labelcolor=INK, handlelength=1.6,
                    borderpad=0.8, labelspacing=0.6)
    leg.get_frame().set_facecolor(BG)
    leg.get_frame().set_edgecolor(GRID)
    leg.get_frame().set_linewidth(1)

    fig.savefig(out, dpi=200, facecolor=BG)
    plt.close(fig)
    print("wrote", out)


def main():
    OUTDIR.mkdir(parents=True, exist_ok=True)
    loaded = load_all()

    # Closed-form curves (no Monte Carlo): each step's cost-to-first-hit is Exponential(λ),
    # the incident is their hypoexponential sum -- so the incident is <= every step at all X.
    lams = [step_rate(c, w) for c, w in loaded]
    xs = np.exp(np.linspace(np.log(0.25), np.log(4096), 300))   # fixed $0.25-$4096 window

    probe = np.exp(np.linspace(np.log(1), np.log(2 ** 16), 4000))   # wide grid for the quantiles
    iyp = incident_cdf(lams, probe)
    for (label, _sub, _dirs), (costs, wins), lam in zip(STEPS, loaded, lams):
        med = np.log(2) / lam if lam > 0 else float("inf")
        print(f"{label:8} n={len(costs):4d}  p={wins.mean():.4f}  $/audit={costs.mean():.2f}  "
              f"median ${med:,.0f}")
    print("\nWHOLE INCIDENT -- run each step until it lands, then move on:")
    for q in (0.50, 0.80, 0.90, 0.95):
        print(f"  P>={q:.2f} of recreating all four:  ${quantile(iyp, probe, q):,.0f}")

    draw(loaded, lams, xs, out=OUTDIR / "part2_cost_ci.png")


if __name__ == "__main__":
    main()
