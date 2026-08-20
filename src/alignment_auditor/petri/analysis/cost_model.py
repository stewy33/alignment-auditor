"""Per-audit dollar cost and outcome, joined from a run's conv/ and scored/ logs.

Shared by plot_steps_1234.py (outcomes) and plot_cost_scaling.py (outcomes + cost).

WHERE THE COST COMES FROM
Inspect records `model_usage` per sample: a {model -> ModelUsage} dict with input/output,
cache read/write and reasoning token splits. A run's spend has two parts, and they live in
different files:

  * auditor + target (glm52)  -> the conv/ log, which is the actual rollout
  * judge (opus48)            -> each scored/ log, one per judge

`score()` writes a scored log by COPYING the conv log -- and it does NOT add the judge's own
usage. A rescored sample's `model_usage` (and the log's eval-level `stats.model_usage`)
therefore describes the glm ROLLOUT only, repeated identically in every judge's file. Two
consequences: summing whole scored logs would count the rollout once per judge, and the judge's
spend is simply absent. So we take glm usage from conv/ only, and get judge spend from the
score metadata `judge_usage` that custom_judge.py now records -- falling back to a calibrated
estimate for runs scored before it did (see estimated_judge_cost below). An INLINE judge is
the exception: its usage lands on the conversation sample and is measured exactly.

REASONING TOKENS are already part of `output_tokens` (they are output), so they are not
priced separately -- doing so would double-count them.
"""

import json
from dataclasses import dataclass
from pathlib import Path

from inspect_ai.log import list_eval_logs, read_eval_log

LOGS = Path("logs")
# Reading a run means parsing every .eval in it -- ~65MB each, minutes per plot. The records we
# extract are a few hundred bytes per audit, so cache them keyed on the (path, mtime, size) of
# every log that fed them: touch or rescore a log and the key changes and the run is re-read.
CACHE = Path("results/.cache/cost_model")


@dataclass(frozen=True)
class Price:
    """USD per 1M tokens."""

    inp: float
    out: float
    cache_read: float
    cache_write: float


# GLM 5.2 via OpenRouter -- the Z.AI first-party endpoint, which is OpenRouter's headline rate
# for this model (2026-08-20). NB OpenRouter routes across ~30 providers whose rates span
# $0.50-$2.31 /1M input, so absolute dollars carry that spread; the SHAPE of the scaling curve
# does not, since every step is priced identically. Cache WRITE is not published for any GLM 5.2
# endpoint -- priced at the input rate (and the runs report CW=0 regardless).
GLM52 = Price(inp=1.40, out=4.40, cache_read=0.26, cache_write=1.40)

# Claude Opus 4.8. Same $5/$25 per 1M on Anthropic-direct and via OpenRouter; cache read is
# 0.1x input, cache write 1.25x input.
OPUS48 = Price(inp=5.00, out=25.00, cache_read=0.50, cache_write=6.25)

PRICES = {
    "openrouter/z-ai/glm-5.2": GLM52,
    "anthropic/claude-opus-4-8": OPUS48,
    "openrouter/anthropic/claude-opus-4.8": OPUS48,
}


def usage_cost(model: str, u) -> float:
    """USD for one sample's usage of one model. Unknown models cost 0 and are reported."""
    price = PRICES.get(model)
    if price is None:
        return 0.0
    return (
        (u.input_tokens or 0) * price.inp
        + (u.output_tokens or 0) * price.out
        + (u.input_tokens_cache_read or 0) * price.cache_read
        + (u.input_tokens_cache_write or 0) * price.cache_write
    ) / 1_000_000


def _is_judge_model(model: str) -> bool:
    return "claude" in model or "opus" in model


# --- estimating judge spend on runs scored before it was recorded --------------------------
# A custom-judge RESCORING pass records no token usage (score() copies the conv log; the judge
# runs outside it). custom_judge.py now writes `judge_usage` into the score metadata, but every
# run scored before that -- steps 2 and 3 included -- has no judge tokens on disk at all.
#
# Calibrated on 260819_rung4_hf_cheat_rubsub_n128, which used an INLINE gating judge and so has
# real per-sample Opus usage next to the transcript it read (n=42):
#     mean auditor-stream 276,280 chars  ->  162,974 judge input tokens, 780 output
#     => 0.59 judge input tokens per character of auditor stream
# Applied to a run's own per-sample character count, so a step with shorter audits is charged
# less. Priced at the plain input rate: a rescoring pass sends each transcript once, with no
# cache_control and no reuse, so there is no cache discount to claim.
JUDGE_TOKENS_PER_CHAR = 0.59
JUDGE_OUTPUT_TOKENS = 780


def estimated_judge_cost(chars: int) -> float:
    return (chars * JUDGE_TOKENS_PER_CHAR * OPUS48.inp + JUDGE_OUTPUT_TOKENS * OPUS48.out) / 1_000_000


def load_run(run_dir: str, cost_judges: tuple[str, ...] = ("custom", "validity")) -> list[dict]:
    """Per-audit records for one run: {level, scenario_valid, cost_rollout, cost_judge, cost}.

    Joined across logs by (sample id, epoch). `level` comes from the STRICT behaviour judge
    (filename contains 'custom' but not 'broad'), `scenario_valid` from the validity judge.
    Judge spend is counted only for the judges named in `cost_judges` -- by default the two
    that the reported metric actually depends on, so the secondary broad judge (a second read
    on the same transcripts) does not inflate the cost of producing the headline number.
    """
    root = LOGS / run_dir
    # list_eval_logs returns URIs ("file:/abs/path"), not filesystem paths -- strip the scheme
    # before stat()ing. read_eval_log takes either, which is why only the cache key noticed.
    conv_paths = [Path(i.name.removeprefix("file:")) for i in list_eval_logs(str(root / "conv"))]
    paths = sorted(conv_paths) + sorted(root.glob("scored/*.eval"))
    stamp = [[str(q), q.stat().st_mtime_ns, q.stat().st_size] for q in paths]
    key = CACHE / f"{run_dir}__{'-'.join(sorted(cost_judges))}.json"
    if key.exists():
        cached = json.loads(key.read_text())
        if cached.get("stamp") == stamp:
            return cached["records"]

    by_key: dict = {}

    # --- rollout (auditor + target) from the conversation log -----------------------------
    for p in sorted(list_eval_logs(str(root / "conv")), key=lambda i: i.name):
        log = read_eval_log(p.name)
        for s in log.samples or []:
            d = by_key.setdefault((str(s.id), s.epoch), {"cost_rollout": 0.0, "cost_judge": 0.0})
            for model, u in (s.model_usage or {}).items():
                if _is_judge_model(model):
                    # An INLINE judge's usage is recorded here, on the conversation sample.
                    d["cost_judge"] += usage_cost(model, u)
                    d["judge_measured"] = True
                else:
                    d["cost_rollout"] += usage_cost(model, u)
            d["chars"] = sum(len(str(getattr(m, "text", "") or "")) for m in (s.messages or []))

    # --- scores + judge spend from each scored log ----------------------------------------
    for p in sorted(root.glob("scored/*.eval")):
        fn = p.name
        is_validity = "validity" in fn
        is_broad = "broad" in fn
        is_strict = ("custom" in fn) and not is_broad
        kind = "validity" if is_validity else ("broad" if is_broad else "custom")
        log = read_eval_log(str(p))
        for s in log.samples or []:
            d = by_key.setdefault((str(s.id), s.epoch), {"cost_rollout": 0.0, "cost_judge": 0.0})
            if kind in cost_judges:
                # Real usage if custom_judge.py recorded it; otherwise the calibrated estimate.
                for v in (s.scores or {}).values():
                    u = ((v.metadata or {}).get("judge_usage")) or {}
                    if u.get("model"):
                        price = PRICES.get(u["model"], OPUS48)
                        d["cost_judge"] += (
                            (u.get("input_tokens") or 0) * price.inp
                            + (u.get("output_tokens") or 0) * price.out
                            + (u.get("input_tokens_cache_read") or 0) * price.cache_read
                            + (u.get("input_tokens_cache_write") or 0) * price.cache_write
                        ) / 1_000_000
                        d["judge_measured"] = True
                        break
                else:
                    d.setdefault("judge_estimated_passes", 0)
                    d["judge_estimated_passes"] += 1
            for v in (s.scores or {}).values():
                val = v.value
                if not isinstance(val, dict):
                    continue
                if "level" in val and is_strict:
                    d["level"] = int(val["level"])
                if "level" in val and is_broad:
                    d["level_broad"] = int(val["level"])
                if "scenario_valid" in val and is_validity:
                    d["scenario_valid"] = int(val["scenario_valid"])

    out = []
    for d in by_key.values():
        d["cost_judge"] += estimated_judge_cost(d.get("chars", 0)) * d.get("judge_estimated_passes", 0)
        d["cost"] = d["cost_rollout"] + d["cost_judge"]
        out.append(d)
    key.parent.mkdir(parents=True, exist_ok=True)
    key.write_text(json.dumps({"stamp": stamp, "records": out}))
    return out
