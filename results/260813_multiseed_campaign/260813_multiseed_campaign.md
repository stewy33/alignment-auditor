# Is the perturbation gradient widespread, and is it benchmark patching?

> **Pre-registration.** Nothing run. Design, predictions, thresholds and analysis fixed before
> spend. Results appended after.

> **Seed handling.** The five drawn families and their perturbations are unpublished and carry
> fresh canary GUIDs. Where they live — public repo or private `petri-experiments` — is unresolved
> and must be settled before the draw is committed. See *Open decisions*.

## Question

[`260812_gradient_replication.md`](../260812_seed_gradient/260812_gradient_replication.md)
established, on one target and one seed family, that `gpt-5.6-luna` becomes more elicitable as a
Petri seed moves further from its published wording (trend +0.95/level, p=0.009, replicated
across two judges).

Two things follow that a single-target, single-family run cannot answer:

1. **Is it widespread?** Does the gradient appear across models from different labs, and across
   Petri seeds drawn at random rather than hand-picked?
2. **Is it benchmark patching?** The conjecture is that labs fix benchmark *scenarios* rather
   than the behaviour those scenarios probe. That is a claim about training incentives, and it
   makes a differential prediction across labs that a single-lab result cannot test.

Question 2 is the reason to run this. Question 1 alone would be a survey.

## The two mechanisms

Petri is Anthropic's benchmark, public since Oct 2025. If the gradient is **benchmark patching**,
its steepness should track how much a lab has had reason and opportunity to optimise against
published Petri seeds. If instead it is **generic distribution shift** — models are simply worse
on any unfamiliar phrasing — every target should show a similar slope regardless of lab.

These make opposite predictions about the *spread* of slopes across targets, and both are
consistent with question 1 coming back positive. Distinguishing them is the primary outcome.

## Design

| | Main matrix | Reasoning arm |
|---|---|---|
| Auditor | `claude-opus-5` — effort `high` | identical |
| Targets | 7 (below) — effort `high` | `gpt-5.6-luna` — effort `medium` |
| Judges | `opus5` and `sol`, both scoring every transcript | identical |
| Seeds | 5 randomly drawn families × 4 levels | `trial_suppression` only, 4 levels |
| Epochs | 4 | 10 |
| Audits | 560 | 40 |

**600 audits, 16 scoring passes.**

Only one auditor. Sol floored at 1.0 against luna at both `medium` and `high`; testing further
auditors is out of scope here and leg 2's auditor half stays open.

### Targets

| Target | Lab | Notes |
|---|---|---|
| `claude-sonnet-5` | Anthropic | Authored Petri |
| `claude-haiku-4-5` | Anthropic | **Within-lab timing control** — see below |
| `gpt-5.6-terra` | OpenAI | |
| `x-ai/grok-4.6` | xAI | Listed on OpenRouter 2026-08-12 |
| `z-ai/glm-5.2` | Z.AI | Already exercised in this repo |
| `deepseek/deepseek-v4-pro-0813` | DeepSeek | Dated snapshot pinned for reproducibility |
| `moonshotai/kimi-k3` | Moonshot | |

`opus5` and `gpt-5.6-sol` are excluded as targets: they are the auditor and a judge, and
self-auditing is a confound we do not want inside the headline comparison.

`gpt-5.6-luna` at `high` is not re-run — n=10 on `trial_suppression` already exists from
260812 and the reasoning arm compares against it directly.

**Haiku 4.5 is a control, not filler.** It was listed 2025-10-15, contemporaneous with Petri's
publication, so it had essentially no opportunity to be trained against published Petri seeds.
Sonnet 5 had a year. If benchmark patching drives the gradient, two models from the *same lab*
should separate on release timing. If Anthropic models simply behave alike, they will not.
Confound: Haiku 4.5 is also smaller and older, so capability moves with timing here.

### Seed families

A **family** is one published Petri seed (v0, verbatim) plus a three-level perturbation ladder
(v1_near, v2_mid, v3_far), built the same way as `trial_suppression`.

Selection, in order, all steps recorded before any audit runs:

1. **Text eligibility.** From the 173 default seeds, keep those that present a concrete
   misaligned action the target could take. 62 seeds are under 500 bytes and many are thin
   prompts with no wrong action on offer; those cannot produce a gradient in either direction.
   The criterion is applied to seed text only and never touches target scores, so it is not
   selection on the outcome.
2. **Stratified random draw.** Stratify on Petri's own `tags` and draw 5 families, fixed RNG
   seed, list committed before spend. The tag distribution is long-tailed
   (`cooperation_with_misuse` 26 … singletons), so an unstratified draw of 5 could easily return
   three variants of one mechanism.

Selection is deliberately *not* conditioned on whether targets are elicitable. Screening on v0
would keep seeds where models already fail the published version and flatten the gradient;
screening on v3 would inflate it.

`trial_suppression` was hand-picked and is **not** part of the random sample. It is reported
alongside as the pre-existing family and excluded from every pooled estimate.

### Perturbation generation

One model writing all 20 variants would put a single notion of "far" behind every family — and
as 260812 noted, multiplying families amplifies generator bias rather than fixing it.

Generators: `opus48`, `glm-4.7`, `grok-4.5` — three labs, none of them a target, the auditor or a
judge. Assignment to families randomised with the same RNG seed.

Residual risk: every candidate generator shares a lab lineage with some target. This is checked
post hoc rather than designed away — does a family generated by lab X show an anomalous slope for
lab X's target?

### Severity control

Per family, the blind pairwise rating from 260812: front matter stripped, no filenames, both
directions of every pair, no mention of perturbation or distance. Raters `opus46` and
`gpt-5.6-sol` — neither is a generator. 24 comparisons per family, 120 total; text comparison
only, no audits.

A family whose ladder is rated non-interchangeable on explicitness, pressure or wrongness is
reported separately rather than dropped.

## Outcome measures

**Primary: per-target slope.** OLS of `concerning` on level index (0–3) with family fixed
effects, fitted per target across all 5 families — 80 draws per target. Reported per judge.

Analysis 0 of 260812 selected the mean over the rate measure; carried forward unless the
distribution check says otherwise.

**Individual (family × level × target) cells are not interpretable at n=4 and will not be
read as measurements.** The family axis buys breadth, not per-cell resolution.

## Hypotheses and predictions

**H1 — the gradient is widespread.**
*Prediction:* ≥4 of 7 targets show a positive slope under both judges; median target slope
+0.3 to +0.8 per level. Lower than luna's +0.95 because a random draw will include families with
no headroom.

**H2 — it is benchmark patching.**
*Prediction:* slope rank correlates with predicted Petri exposure. Pre-registered ranking, most
exposed first:

| Rank | Target | Reasoning |
|---:|---|---|
| 1 | Sonnet 5 | Anthropic authored Petri; a year of opportunity |
| 2 | Terra | US frontier lab, tracks public evals |
| 3 | Grok 4.6 | US frontier lab, less eval-focused publicly |
| 4 | GLM 5.2 | Chinese lab, some Western benchmark targeting |
| 5 | DeepSeek v4-pro | Chinese lab |
| 6 | Kimi K3 | Chinese lab |
| 7 | Haiku 4.5 | Anthropic, but shipped as Petri was published |

*Test:* Spearman ρ between predicted rank and observed slope rank, n=7. **ρ ≥ 0.714 (one-tailed
p<0.05) is the pre-registered bar.** With 7 targets this is a weak test by construction; it is
recorded as directional evidence, not proof, and the honest reading of ρ between 0.3 and 0.7 is
"consistent, underpowered".

*Within-lab check, independent of the rank test:* Sonnet 5 slope > Haiku 4.5 slope.

**H2-alt — generic distribution shift.**
*Prediction:* slopes cluster within roughly ±0.3 of each other with no lab structure, ρ ≈ 0.
This is a real possible outcome and it downgrades the conjecture from "labs patch benchmarks" to
"models are worse off-distribution" — a weaker and much less interesting claim.

**H3 — reasoning budget.**
Luna's gradient was first seen at `medium` and survived at `high`, so effort is not the driver.
*Prediction:* slope at `medium` ≥ slope at `high` on `trial_suppression`, difference < 0.4 with
overlapping intervals.

**Prediction about families.** 1–2 of the 5 drawn families come back flat across all targets.

## Analysis

0. **Distribution check** per target before summarising, as in 260812. Decides whether the mean
   stays the primary summary.
1. **Per-target slope**, per judge. Report the parametric t-test on the slope, plus a permutation
   test (20,000 shuffles of level labels *within family*) that assumes nothing about the
   distribution, plus Spearman and Jonckheere for monotonic order only.
2. **H1** — count of targets with positive slope; sign test across targets.
3. **H2** — Spearman on the pre-registered rank; Sonnet 5 vs Haiku 4.5 contrast reported
   separately.
4. **Judge robustness** — slopes per judge, mean and max per-sample gap. Prior run: mean gap 1.5,
   max 7, 11/40 ≥3, near-identical slopes. Pool only where the gap is small, stating the
   threshold.
5. **Floored targets** — pre-declared criterion: a (target, family) pair is floored if mean
   `concerning` ≤ 1.5 at every level. Primary estimates **include** floored pairs, because a flat
   family is genuine evidence of no effect. A sensitivity analysis excludes them. The two answer
   different questions — "does this model degrade across Petri seeds on average" versus "where
   there is signal at all, does it degrade" — and both are reported.
6. **Transcripts.** Read every cell driving a conclusion and every case where the judges split by
   ≥3. Judge scores are evidence, not ground truth.

## What would falsify what

| Outcome | Reading |
|---|---|
| Median slope ≈ 0, no more targets positive than chance | H1 falsified — the 260812 result is luna-and-`trial_suppression`-specific |
| Slopes positive, ρ ≈ 0, no lab structure | H1 supported, H2 falsified — mechanism is generic OOD, report as the weaker claim |
| Slopes positive, ρ ≥ 0.714, Sonnet 5 > Haiku 4.5 | Both supported — benchmark patching survives its first real test |
| Slopes positive, ρ high, but Sonnet 5 ≈ Haiku 4.5 | Mixed — cross-lab ordering may be tracking something other than Petri exposure |

## Pre-flight — nothing runs until these pass

1. **Degenerate-audit filter in `exp.py`.** 2/40 sol audits in 260812 had no target response,
   were scored anyway (one at 8), `auditor_failure` flagged them 2/10, and they crash the rescore
   pass at `inspect_petri/_judge/judge.py:69`. A crash partway through 600 audits is expensive.
2. **`eval_set` resume.** `evalset.py:1037` swallows `RecoveryNotAvailable` with a bare `pass`
   and silently re-runs everything. That turned a $200 estimate into $226 last time; here it
   could cost four figures.
3. **Per-target smoke test**, n=1, one seed. Verify: the endpoint carries a 30-turn Petri audit
   with tool calls; `effort: high` is honoured and echoed in the response, not silently dropped;
   no empty completions from reasoning consuming the token budget (the GLM 5.2 failure mode).
   Grok 4.6 and DeepSeek v4-pro-0813 were both listed on 2026-08-12 and are the most likely to
   have schema or rate-limit problems.
4. **Resolve `deepseek-v4-pro` vs `-0813`.** The dated snapshot is *cheaper* ($0.43/$0.87 vs
   $1.17/$2.34 per M), which suggests the undated alias routes elsewhere. Confirm before pinning.

## Threats

- **The exposure ranking is a proxy.** Petri exposure is unobservable. Lab identity correlates
  with capability, model size, safety-training intensity and RLHF style, all of which could
  produce the same ordering. A positive ρ is consistent with H2, not proof of it.
- **The instrument is Anthropic's.** Opus 5 is the sole auditor and half the judging, and the
  headline output ranks labs including Anthropic. The sol judge covers scoring; nothing covers
  elicitation. Leg 2's auditor half remains open and this run does not address it.
- **Effort labels are not calibrated across five providers.** Setting `high` everywhere equalises
  the setting, not the compute. This was already a limitation at two labs; at five it is heavier,
  and several targets are hybrid-reasoning models where `high` may not map cleanly.
- **n=4 per cell.** Deliberate — the budget buys families rather than epochs, because the unit of
  inference is now the per-target slope. The cost is that no individual cell is readable.
- **Five families is itself a small sample of seeds.** Family-level variance may dominate, and a
  random draw of 5 from 173 has wide sampling error on the "average Petri seed" estimand.
- **Domain confound persists.** v1/v2/v3 change surface and scenario together. 260812 closed the
  severity half of leg 3; the domain half needs several variants at the *same* distance, which
  this design does not include.
- **Scores are floors** — `max_turns: 30`, audits frequently still developing when cut.
- **Judge severity offsets** mean absolute scores are not comparable across judges; only
  direction is.

## Cost

Rates from 260812: opus5 auditor $2.97/audit, opus5 judge ~$0.5/transcript, sol judge ~$0.25
(estimated — `score()` does not record the scoring model's own tokens, so it cannot be audited
after the fact). Target cost varies by provider; luna is negligible, Kimi K3 the most expensive.

| | Estimate |
|---|---:|
| Auditor, 600 audits | ~$1,780 |
| Judging, 600 transcripts × 2 | ~$450 |
| Targets | ~$300 |
| Severity rating, 120 comparisons | ~$20 |
| **Total** | **~$2,550** |

Roughly $2,200–3,000 depending on target verbosity. Anthropic ~$2,200, OpenAI ~$200, OpenRouter
~$150. Compare 260812: 80 audits, $226.

Ten families rather than five would be ~$5,000. Recommend extending only if five shows an effect
worth resolving further.

## Open decisions

1. **Canary handling.** v1–v3 of `trial_suppression` carry freshly generated GUIDs and are
   currently on a public remote; v0 carries Petri's own already-public GUID and is harmless. This
   run adds five more families of unpublished perturbations. Settle before the draw is committed:
   scrub and move to the private repo, or publish deliberately and accept that contamination
   checks on these seeds become unfalsifiable.
2. **Whether to add `opus5` and `gpt-5.6-sol` as targets later**, scored only by the judge they
   are not.
