"""Two-line P(>=1 valid elicitation) vs cost: the memory arm against the iid baseline.

    uv run python -m alignment_auditor.petri.analysis.plot_memory_scaling

Same axes and success definition as plot_cost_scaling (rung >= 3 AND scenario_valid, dollars of
auditor + target + judge -- plus, for the memory arm, the Reviewer). The two lines are built
differently on purpose (design 6.7):

  * BASELINE (iid): best-of-n bootstrap over an exchangeable audit pool -- P(any of n audits
    lands) vs the mean cost of n audits. Reused pool, no new spend. If the pool's logs are not
    present locally, a clearly-labelled STAND-IN is drawn from the published per-audit rate and
    cost (results/260821_steps1234), to be swapped for the real bootstrap once the logs return.

  * MEMORY (this design): the empirical CDF of "cost to the FIRST valid hit". Memory audits are
    NOT exchangeable (audit N depends on 1..N-1), so this line is a trajectory over R replicate
    runs, never a bootstrap over audits. Each run collapses to one number T = cumulative
    (rollout + judge + Reviewer) cost at its first valid hit (inf if it never hits); the line is
    P(T <= C) = fraction of runs that have landed a hit by budget $C, with a Wilson band across
    runs. Runs that never hit are right-censored: past the shortest run's budget the curve
    honestly plateaus below 1.
"""

from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from .cost_model import load_memory_run, load_run
from .plot_cost_scaling import INK, INK_MUTED, SURFACE, best_of_n, style

MEMORY_RUN = "260821_step3_memory"
BASELINE_POOL = "260819_step3_exploit_share_n256"
# Stand-in for the baseline when its pool logs are not present locally (results/260821_steps1234).
BASELINE_STANDIN_P = 0.23
BASELINE_STANDIN_COST = 1.17

OUTDIR = Path("results/260821_memory_step3/figures")
MEM_COLOUR = "#a35f14"
BASE_COLOUR = "#184f95"
NS = [1, 2, 4, 8, 16, 32, 64, 128, 256]


def cost_to_first_hit(records: list[dict]) -> list[float]:
    """One T per replicate: the cost through the generation that lands its first valid hit
    (inf if it never hits).

    Counts the WHOLE hitting generation, not just up to the first hitting audit: the wave is
    parallel, so every audit in that generation was launched and paid for. This is the honest,
    conservative x-value -- it does not flatter the memory arm by pretending it could have stopped
    mid-wave.
    """
    reps: dict = {}
    for r in records:
        reps.setdefault(r["rep"], []).append(r)
    out = []
    for rep, rs in sorted(reps.items()):
        rs = sorted(rs, key=lambda r: (r["gen"], r["order"]))
        hit_gen = next((r["gen"] for r in rs if r["level"] >= 3 and r["scenario_valid"] == 1), None)
        if hit_gen is None:
            out.append(float("inf"))
        else:
            out.append(sum(r["cost"] for r in rs if r["gen"] <= hit_gen))
    return out


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return 0.0, 1.0
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return max(0.0, c - h), min(1.0, c + h)


def memory_cdf(Ts: list[float], budgets: np.ndarray):
    R = len(Ts)
    ys, los, his = [], [], []
    for C in budgets:
        k = sum(1 for t in Ts if t <= C)
        ys.append(k / R)
        lo, hi = wilson(k, R)
        los.append(lo), his.append(hi)
    return np.array(ys), np.array(los), np.array(his)


def baseline_curve(budgets: np.ndarray):
    """(P by budget, label, is_standin). Real bootstrap if the pool is on disk, else a stand-in."""
    recs = [r for r in load_run(BASELINE_POOL) if "level" in r and "scenario_valid" in r] \
        if (Path("logs") / BASELINE_POOL).exists() else []
    if recs:
        costs = np.array([r["cost"] for r in recs], dtype=float)
        wins = np.array([r["level"] >= 3 and r["scenario_valid"] == 1 for r in recs], dtype=bool)
        xs, ys = [], []
        for n in NS:
            x, y, _, _ = best_of_n(costs, wins, n)
            xs.append(x), ys.append(y)
        # Interpolate onto the shared budget grid (P is monotone in cost).
        P = np.interp(budgets, xs, ys, left=0.0, right=ys[-1])
        return P, f"baseline (iid, best-of-n over n={len(recs)})", False
    # Stand-in: analytic best-of-n from the published rate/cost.
    n = budgets / BASELINE_STANDIN_COST
    P = 1 - (1 - BASELINE_STANDIN_P) ** n
    return P, "baseline (iid, from published rates -- stand-in)", True


def crossing_budget(budgets, mem_P, base_P):
    """Smallest budget at which the memory line reaches or passes the baseline and stays there."""
    ahead = mem_P >= base_P
    for i in range(len(budgets)):
        if ahead[i] and ahead[i:].all():
            return float(budgets[i])
    return None


def main() -> None:
    import argparse

    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--run", default=MEMORY_RUN, help="memory run dir under logs/")
    ap.add_argument("--out", default=str(OUTDIR / "260821_memory_step3.png"), help="output PNG path")
    args = ap.parse_args()

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    records = load_memory_run(args.run)
    if not records:
        print(f"!! no memory records under logs/{args.run}/ -- run the memory experiment first")
        return
    Ts = cost_to_first_hit(records)
    R = len(Ts)
    finite = [t for t in Ts if np.isfinite(t)]
    total_spend = sum(r["cost"] for r in records)
    print(f"memory run {MEMORY_RUN}: R={R} replicate(s), {len(records)} audits, ${total_spend:.2f} total")
    print(f"  cost-to-first-hit per run: {[round(t, 2) if np.isfinite(t) else 'inf' for t in Ts]}")

    hi_budget = max(max(finite) if finite else total_spend, total_spend)
    budgets = np.exp(np.linspace(np.log(max(min(r['cost'] for r in records), 0.5)), np.log(hi_budget * 1.2), 200))
    mem_P, mem_lo, mem_hi = memory_cdf(Ts, budgets)
    base_P, base_label, standin = baseline_curve(budgets)

    fig, ax = plt.subplots(figsize=(9.5, 6))
    fig.patch.set_facecolor(SURFACE)
    style(ax)
    ax.plot(budgets, base_P, ls="--" if standin else "-", color=BASE_COLOUR, linewidth=2, label=base_label, zorder=3)
    ax.plot(budgets, mem_P, color=MEM_COLOUR, linewidth=2.4, label=f"memory (R={R})", zorder=5)
    if R > 1:
        ax.fill_between(budgets, mem_lo, mem_hi, color=MEM_COLOUR, alpha=0.15, linewidth=0, zorder=4)

    cross = crossing_budget(budgets, mem_P, base_P)
    if cross is not None:
        ax.axvline(cross, color=INK_MUTED, linewidth=1, ls=":", zorder=2)
        ax.annotate(f"crossing ${cross:.0f}", (cross, 0.05), fontsize=8, color=INK_MUTED,
                    rotation=90, va="bottom", ha="right")
        print(f"  crossing budget (memory reaches/passes baseline and stays): ${cross:.2f}")
    else:
        print("  memory line does not dominate the baseline across the budget range")

    ax.set_xscale("log", base=2)
    lo, hi = ax.get_xlim()
    ticks = [2.0 ** k for k in range(int(np.floor(np.log2(lo))), int(np.ceil(np.log2(hi))) + 1)]
    ax.set_xticks(ticks)
    ax.set_xticklabels([f"${t:g}" if t >= 1 else f"${t:.2f}" for t in ticks])
    ax.set_xlabel("cost of the elicitation budget (USD, auditor + target + judges + reviewer)",
                  fontsize=10, color=INK_MUTED)
    ax.set_ylabel("P(at least one valid elicitation)", fontsize=10, color=INK_MUTED)
    ax.set_ylim(-0.02, 1.02)
    ax.legend(frameon=False, fontsize=9, loc="lower right")
    fig.tight_layout()
    fig.savefig(out_path, dpi=150, facecolor=SURFACE)
    print("wrote", out_path)


if __name__ == "__main__":
    main()
