"""How much does `stop_at_successful_n` actually bias r/N? Simulate the exact rule.

    uv run python -m alignment_auditor.petri.analysis.stopping_bias

Steps 1 and 4 used adaptive sampling, so their rates are computed over a denominator the
stopping rule chose -- which is why they are flagged as biased. But the rule is gentler than
textbook sequential stopping, and the size of the bias is an empirical question we can answer
with no API calls at all.

THE MECHANISM (adaptive.py): at most `max_parallel` (W) audits are in flight. Audits are
LAUNCHED blind to outcome. When the Kth success lands, `schedule_sample` returns EarlyStop for
every audit NOT YET STARTED -- but the up-to-(W-1) already running are not cancelled, they run
to completion and are KEPT. So the logged sample is:

    [ the T completions that produced the Kth success ]  +  [ the W-1 in flight at that moment ]

The first block is negative-binomial-truncated: it ends exactly on a success, so K/T is biased
UP as an estimate of p. The second block was launched before any of it was known and is a clean
iid sample of p. r/N mixes the two, and which way it lands depends on W, K and p.

We simulate the rule over a grid of true p, then invert the resulting E[r/N] curve to get a
bias-corrected estimate for the observed r/N. Reported alongside the raw rate rather than
replacing it -- this corrects the denominator, it does not conjure the precision of a real
fixed-n run (the CI is still the CI of ~21 or ~41 audits).
"""

import numpy as np

RNG = np.random.default_rng(7)
B = 20000


def simulate(p: float, window: int, target_k: int, cap: int, reps: int = B) -> tuple[float, float]:
    """Mean (r/N, N) under the real stopping rule for a true rate p."""
    ratios = np.empty(reps)
    ns = np.empty(reps)
    for i in range(reps):
        launched, completed, successes = window, 0, 0
        outcomes = []
        stopped = False
        while completed < launched:
            hit = RNG.random() < p
            outcomes.append(hit)
            completed += 1
            if hit:
                successes += 1
            if not stopped and successes >= target_k:
                stopped = True  # no further launches; in-flight run to completion
            if not stopped and launched < cap:
                launched += 1
        ratios[i] = sum(outcomes) / launched
        ns[i] = launched
    return float(ratios.mean()), float(ns.mean())


def invert(observed: float, window: int, target_k: int, cap: int) -> tuple[float, float]:
    """Find true p whose E[r/N] matches the observed rate. Returns (p_hat, bias at p_hat)."""
    grid = np.linspace(0.01, 0.99, 40)
    curve = np.array([simulate(p, window, target_k, cap, reps=4000)[0] for p in grid])
    p_hat = float(np.interp(observed, curve, grid))
    exp_at, _ = simulate(p_hat, window, target_k, cap)
    return p_hat, exp_at - p_hat


# (label, window=max_parallel, K=stop_at_successful_n, cap=epochs, observed rung>=3 rate, observed N)
CASES = [
    ("Step 1  260814_ladder_glm52_L0", 16, 2, 128, 0.667, 21),
    ("Step 4  260819_rung4_hf_cheat_rubsub_n128", 32, 8, 128, 0.366, 41),
]


def main() -> None:
    for label, w, k, cap, obs, obs_n in CASES:
        print(f"\n=== {label}")
        print(f"    rule: window={w}, stop at {k} successes, cap {cap}; observed r/N={obs:.3f} over N={obs_n}")
        print(f"    {'true p':>8} {'E[r/N]':>8} {'bias':>7} {'E[N]':>7}")
        for p in (0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8):
            mean_ratio, mean_n = simulate(p, w, k, cap, reps=4000)
            print(f"    {p:8.2f} {mean_ratio:8.3f} {mean_ratio - p:+7.3f} {mean_n:7.1f}")
        p_hat, bias = invert(obs, w, k, cap)
        print(f"    -> bias-corrected p for observed {obs:.3f}: {p_hat:.3f}  (raw overstates by {obs - p_hat:+.3f})")


if __name__ == "__main__":
    main()
