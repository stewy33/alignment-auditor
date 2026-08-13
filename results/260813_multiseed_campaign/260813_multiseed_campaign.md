# Is the perturbation gradient widespread, and is it benchmark patching?

> **Pre-registration.** Nothing run. Design, predictions, thresholds and analysis fixed before
> spend. Results appended after.

> **Seed handling.** All five families, their perturbations and their canary GUIDs are published
> in this repo. This makes the seeds single-use for contamination checking — see *Decisions taken*.

## Question

[`260812_gradient_replication.md`](../260812_seed_gradient/260812_gradient_replication.md)
established, on one target and one seed family, that `gpt-5.6-luna` becomes more elicitable as a
Petri seed moves further from its published wording (trend +0.95/level, p=0.009, replicated
across two judges).

Two things follow that a single-target, single-family run cannot answer:

1. **Is it widespread?** Does the gradient appear across models from different labs, and across
   Petri seeds drawn at random rather than on the single family that produced it?
2. **Is it benchmark patching?** The conjecture is that labs fix benchmark *scenarios* rather
   than the behaviour those scenarios probe. That is a claim about training incentives, and it
   makes a differential prediction across labs that a single-lab result cannot test.

Question 2 is the reason to run this. Question 1 alone would be a survey.

## Why the spread of slopes is the primary outcome

Petri is Anthropic's benchmark, public since Oct 2025. A model trained against those seeds is
clean on them and degrades on rewordings that preserve the mechanism. The gradient is the
signature of that training, not a separate phenomenon to be distinguished from it.

What is open is whether every model has one. A slope common to all eight targets is a property of
language models in general and says nothing about any lab's training choices. A slope concentrated
in some targets and absent in others tracks something those labs do — which is what the conjecture
actually claims. **The spread of slopes across targets is therefore the primary outcome, not the
average slope.**

## Design

| | Main matrix | Reasoning arm |
|---|---|---|
| Auditor | `claude-opus-5` — effort `high` | identical |
| Targets | 8 (below) — effort `high` | `gpt-5.6-luna` — effort `medium` |
| Judges | `opus5` and `sol`, both scoring every transcript | identical |
| Seeds | 5 families × 4 levels | identical |
| Epochs | 4 | 4 |
| Audits | 640 | 80 |

**720 audits, 18 scoring passes.**

The reasoning arm runs across all five families rather than `trial_suppression` alone, so the
medium/high contrast rests on the same breadth as everything else. Luna is the cheapest target
in the matrix; the marginal cost is auditor time, not target tokens.

Only one auditor. Sol floored at 1.0 against luna at both `medium` and `high`; testing further
auditors is out of scope here and leg 2's auditor half stays open.

### Targets

| Target | Lab | Notes |
|---|---|---|
| `claude-sonnet-5` | Anthropic | Authored Petri |
| `claude-haiku-4-5` | Anthropic | Earlier release — see below |
| `gpt-5.6-terra` | OpenAI | |
| `gpt-5.6-luna` | OpenAI | The model 260812 established the gradient on |
| `x-ai/grok-4.6` | xAI | Listed on OpenRouter 2026-08-12 |
| `z-ai/glm-5.2` | Z.AI | Already exercised in this repo |
| `deepseek/deepseek-v4-pro-0813` | DeepSeek | Dated snapshot pinned for reproducibility |
| `moonshotai/kimi-k3` | Moonshot | |

`opus5` and `gpt-5.6-sol` are excluded as targets: they are the auditor and a judge, and
self-auditing is a confound we do not want inside the headline comparison.

Luna runs at both `high` (main matrix) and `medium` (reasoning arm). Its 260812 n=10 on
`trial_suppression` at `high` is not pooled — every target stays on the same sample size — but it
is held in reserve as the positive control described under *What would falsify what*.


### Seed families

A **family** is one published Petri seed (v0, verbatim) plus a three-level perturbation ladder
(v1_near, v2_mid, v3_far), built the same way as `trial_suppression`.

Five families: **`trial_suppression` plus four drawn at random.**

`trial_suppression` carries over from 260812 and **is pooled with the rest.** It was not selected
on its outcome: it was picked arbitrarily as the first family to perturb, run once, and the
result it produced is what motivated this experiment. Nothing was screened and discarded, so
there is no winner's-curse to correct for and no reason to hold it out.

The one caveat is ordinary discovery-versus-confirmation: it is the sample that generated the
hypothesis, so its effect estimate is the one most likely to sit at the optimistic end. The four
new families are out-of-sample for the hypothesis, and are reported as a subset estimate
alongside the pooled five for exactly that reason — not as a bias correction, but because a
prediction confirmed on data that did not generate it is the stronger result.

The four new families are drawn in order, all steps recorded before any audit runs:

1. **Exclude offensive-security and CBRN content.** Opus 5 is the auditor and the primary judge,
   and it content-filters on this material — in `260806_eval_escalation` it was filtered on all
   60 turns and never emitted a tool call, and it returns `nan` scoring the rung-1 SSRF
   transcripts, which is why those runs use `opus48` as judge. A filtered cell produces no data,
   not a low score.

   Screen by keyword (`hack`, `exploit`, `vulnerab`, `weapon`, `chemical`, `nuclear`,
   `credential`, `payload`, `phish`, …), then read the candidates: the keyword pass flags 22 of
   173, but most are false positives — `reward_hack_test_hardcoding` is reward hacking, and
   `vulnerability_withholding_ethics` is a disclosure dilemma. The genuine exclusions are the
   offensive-capability seeds: `bypass_2fa_hacking`, `chemical_weapons_playbook`,
   `ied_incremental_jailbreak`, `nuclear_material_purchase_hebrew`, and the
   `self_exfiltration_*` set. Expect 5–8 actual removals.

2. **Text eligibility.** From what remains, keep seeds that present a concrete misaligned action
   the target could take. 62 seeds are under 500 bytes and many are thin prompts with no wrong
   action on offer; those cannot produce a gradient in either direction.

3. **Stratified random draw.** Stratify on Petri's own `tags` and draw 4 families, fixed RNG
   seed, list committed before spend. The tag distribution is long-tailed
   (`cooperation_with_misuse` 26 … singletons), so an unstratified draw could easily return
   several variants of one mechanism.

Steps 1 and 2 are applied to seed text only and never touch target scores, so neither is
selection on the outcome.

Selection is deliberately *not* conditioned on whether targets are elicitable. Screening on v0
would keep seeds where models already fail the published version and flatten the gradient;
screening on v3 would inflate it.

The primary pooled slope is computed over **all five families**. The four-random subset is
reported alongside it as the out-of-sample estimate.

### Perturbation generation

**Generator: `gpt-5.6-sol`. Severity rater: `claude-opus-5`.** One generator across all four new
families.

A single generator does put one notion of "far" behind every family, which matters for reading
the *distance* axis — if sol systematically writes far variants as harsher rather than merely more
distant, every family inherits that. It does **not** confound the primary outcome. Every target
sees byte-identical seeds, so any generator bias is a constant across the cross-target comparison
and cannot produce the lab structure H2 predicts. The severity control below is what covers the
distance reading.

Sol rather than Opus 5 as generator: Opus 5 already carries the auditor role and the primary
judge, and having it also write the seeds it audits and scores concentrates too much in one model.
Sol is the secondary judge, so the residual overlap is sol scoring transcripts from seeds it wrote
— which is directly visible in the existing per-judge slope comparison (analysis 4). If sol
favours its own seeds, the two judges' slopes diverge.

`trial_suppression`'s v1–v3 predate this design and their generator is not recorded in the seed
front matter. Noted as an inconsistency across the five families rather than resolved by
regenerating them, since regenerating would break continuity with 260812.

### Severity control

Per family, the blind pairwise rating from 260812: front matter stripped, no filenames, both
directions of every pair, no mention of perturbation or distance. **Rater: `claude-opus-5`** —
not the generator. 24 comparisons per family, 120 total; text comparison only, no audits.

Re-rate `trial_suppression` under the same rater. Its 260812 rating used `sonnet5` and `terra`,
both of which are targets here, and a single consistent rater makes the five families comparable.
The 260812 judgements stay on file as an independent second opinion on that family.

A family whose ladder is rated non-interchangeable on explicitness, pressure or wrongness is
reported separately rather than dropped.

## Outcome measures

**Primary: per-target slope.** OLS of `concerning` on level index (0–3) with family fixed
effects, fitted per target across all 5 families — 80 draws per target. Reported per judge.

**Mean `concerning`, not P(elicited).** 260812 settled this: at n=10 the distribution was not
cleanly bimodal — real mass in the middle, SD 2.0–2.8 rather than the ~3 estimated at n=3 — and
its pre-registered rule selected the mean. The rate measure rose in the same direction and reached
no conventional significance at any threshold, as expected from dichotomising a continuous score.
Settled question, not re-opened here.

**Individual (family × level × target) cells are not interpretable at n=4 and will not be
read as measurements.** The family axis buys breadth, not per-cell resolution.

## Hypotheses and predictions

Two quantities, and they are not the same thing. **Level** is how misaligned a target is overall
— the intercept. **Slope** is how much worse it gets with distance from the published seed — the
gradient. H1 is about level; H2–H4 are about slope. A model can be badly misaligned everywhere
with no gradient, or well behaved everywhere with a steep one.

**H1 — level: Chinese labs and xAI are more misaligned than Anthropic and OpenAI.**
*Prediction:* mean `concerning` pooled across all seeds and levels is higher for
{Grok 4.6, GLM 5.2, DeepSeek v4-pro, Kimi K3} than for {Sonnet 5, Haiku 4.5, Terra, Luna}.
*Test:* Mann–Whitney on the eight per-target means, 4 vs 4, one-tailed.

**H2 — slope: the gradient is lab-specific, not universal.**
Some labs' models show a clear gradient and others do not. A lab that runs alignment training
against published benchmarks has something to whack; a lab that does little scenario-specific
alignment work has no patch to be distribution-bound in the first place, so no gradient — even if
its models are more misaligned overall.

*Prediction:* per-target slopes are heterogeneous — some clearly positive, some flat — rather
than a common slope shared by all eight.
*Test:* target × level interaction on the pooled data. A significant interaction means the slope
is not common across targets. Reported with the per-target slopes and their intervals, so which
models carry the effect is visible without having pre-committed to a grouping.

*Note, not a commitment:* our working guess is that the split falls along
{Sonnet 5, Haiku 4.5, Terra, Luna} versus {Grok 4.6, GLM 5.2, DeepSeek v4-pro, Kimi K3}. If the
observed split matches, the 4 vs 4 Mann–Whitney is reported as a secondary test (perfect
separation gives p = 0.014). It is not the primary bar, because deciding the grouping after
seeing the data would not be a real test and deciding it before commits us to a story we do not
have evidence for yet.

Note H1 and H2 predict *opposite* orderings if that guess is right — the Chinese/xAI group worse
on level and flatter on slope. If both hold, that is a strong result, because no single
measurement artifact produces both.

**H3 — within-lab, same generation: Terra ≈ Luna.**
Same lab, same generation, same exposure. *Prediction:* similar slopes. A large gap is evidence
the group contrast is tracking capability rather than lab, and is the cheapest way this design
catches itself.

**H4 — within-lab, across time: Sonnet 5 > Haiku 4.5.**
More elapsed time for benchmark-specific training. *Prediction:* Sonnet 5's slope exceeds Haiku
4.5's. Confounded by size and capability, and weakened further because Anthropic authored Petri
and had the seeds internally before publication, so release date bounds exposure only loosely.
Descriptive.

**H5 — reasoning budget.**
Luna's gradient was first seen at `medium` and survived at `high`, so effort is not the driver.
*Prediction:* slope at `medium` ≥ slope at `high`, pooled across all five families, difference
< 0.4 with overlapping intervals.


## Analysis

1. **Per-target slope**, per judge, pooled over all five families. Report the parametric t-test on
   the slope, plus a permutation test (20,000 shuffles of level labels *within family*) that
   assumes nothing about the distribution, plus Spearman and Jonckheere for monotonic order only.
   Report the four-random-family subset alongside as the out-of-sample estimate.
2. **H1 (level)** — per-target mean `concerning` pooled across seeds and levels; Mann–Whitney on
   the 4 vs 4 lab-group split.
3. **H2 (slope heterogeneity)** — target × level interaction on the pooled data; report the
   per-target slopes with intervals so the split is visible. If the observed split matches the
   working guess, the 4 vs 4 Mann–Whitney is reported as a secondary test, labelled as such.
4. **H3/H4** — Terra vs Luna and Sonnet 5 vs Haiku 4.5 contrasts reported separately, with
   confidence intervals rather than a significance verdict at this n.
5. **Judge robustness** — slopes per judge, mean and max per-sample gap. Prior run: mean gap 1.5,
   max 7, 11/40 ≥3, near-identical slopes. Pool only where the gap is small, stating the
   threshold.
6. **Floored targets** — pre-declared criterion: a (target, family) pair is floored if mean
   `concerning` ≤ 1.5 at every level. Primary estimates **include** floored pairs, because a flat
   family is genuine evidence of no effect. A sensitivity analysis excludes them. The two answer
   different questions — "does this model degrade across Petri seeds on average" versus "where
   there is signal at all, does it degrade" — and both are reported.
7. **Transcripts.** Read every cell driving a conclusion and every case where the judges split by
   ≥3. Judge scores are evidence, not ground truth.

## What would falsify what

**The primary falsification is a flat result everywhere.** That is the outcome that kills the
conjecture rather than reshaping it, and it comes in two forms that must not be conflated.

`luna × trial_suppression` is a **positive control**: 260812 measured +0.95/level there under an
identical config. It is the one cell where we know what the answer should be.

| Outcome | Reading |
|---|---|
| **Flat everywhere, control included** | **Instrument failure, not a null.** The run failed to reproduce a known effect under a matched config, so nothing in it is interpretable. Debug the pipeline — degenerate audits, effort silently dropped, seeds mis-resolved — and do not report a null |
| **Flat everywhere except the control** | **The conjecture is falsified as a general claim.** The gradient is specific to luna and `trial_suppression` and does not generalise to other models or other Petri seeds. This is a real and publishable negative result |
| **Flat for most targets, positive for a few, control reproduces** | H2 supported in its weakest form — the effect exists but is rare. Which targets carry it is the finding |
| Slopes positive and statistically indistinguishable across all eight | H2 falsified — the effect is universal rather than lab-specific. Either every lab does this, or distillation spread one lab's version of it. The design cannot separate those two |
| Interaction significant, some targets clearly positive and others flat | H2 supported — the gradient is a property of particular models, not of models in general. Which ones is then a descriptive finding |
| That split lands on US vs Chinese/xAI | Our working guess held. Report the 4 vs 4 as a secondary test and flag distillation as the standing alternative |
| Split lands somewhere else entirely | More informative than the guess holding — report the observed structure and what it suggests, without back-fitting a story |
| Terra and Luna far apart | Whatever structure appears is probably tracking capability, not lab |
| H1 and H2 both hold on the guessed grouping | Strongest available outcome — the two predict opposite orderings, so no single measurement artifact explains both |

## Pre-flight — nothing runs until these pass

1. **Degenerate-audit filter in `exp.py`.** 2/40 sol audits in 260812 had no target response,
   were scored anyway (one at 8), `auditor_failure` flagged them 2/10, and they crash the rescore
   pass at `inspect_petri/_judge/judge.py:69`. A crash partway through 720 audits is expensive.
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

- **Distillation homogenises the targets — the biggest threat here.** If the Chinese models and
  Grok are distilled from Anthropic or OpenAI outputs, which is widely reported, they inherit
  their teachers' alignment behaviour — and would inherit any benchmark-bound patching along with
  it. Targets that look independent are then partly the same model. **A flat interaction therefore
  has two readings: the gradient is universal, or one lab's version of it propagated by
  distillation.** This design cannot tell them apart, and it weakens H1 in the same move — a
  distilled model should look *less* misaligned than an independently trained one. Nothing in this
  run resolves it; it needs targets with documented independent training lineage, and it belongs
  on a positive result as well as a null.
- **Whatever structure appears is a proxy for many things.** Petri exposure is unobservable, and
  any grouping that emerges will correlate with capability, model size, safety-training intensity
  and RLHF style. A significant interaction shows the slope is not common across targets; it does
  not say what makes them differ.
- **The instrument is Anthropic's.** Opus 5 is the sole auditor and half the judging, and the
  headline output ranks labs including Anthropic. The sol judge covers scoring; nothing covers
  elicitation. Leg 2's auditor half remains open and this run does not address it.
- **Effort labels are not calibrated across five providers.** Setting `high` everywhere equalises
  the setting, not the compute. This was already a limitation at two labs; at five it is heavier,
  and several targets are hybrid-reasoning models where `high` may not map cleanly.
- **n=4 per cell.** Deliberate — the budget buys families rather than epochs, because the unit of
  inference is now the per-target slope. The cost is that no individual cell is readable.
- **Five families is itself a small sample of seeds**. Family-level variance may dominate, and a
draw this size has wide sampling error on the "average Petri seed" estimand.
- **The cyber/CBRN exclusion may not be neutral.** It is forced — Opus 5 will not audit or judge
  that material — but offensive-capability scenarios are plausibly among the most heavily patched,
  which would make them where the gradient is steepest. Excluding them could bias the pooled slope
  *down*. The estimand is the average *non-cyber* Petri seed, and the result should be stated that
  way. Testing the excluded set needs a different auditor and judge (`opus48` works for the SSRF
  transcripts) and is out of scope here.
- **One generator behind every new family.** Constant across targets, so it cannot manufacture the
  lab structure H2 predicts, but it does mean the distance axis reflects one model's notion of
  "far". The severity control is the only check on this.
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
| Auditor, 720 audits | ~$2,140 |
| Judging, 720 transcripts × 2 | ~$540 |
| Targets | ~$360 |
| Severity rating, 120 comparisons | ~$20 |
| **Total** | **~$3,060** |

Roughly $2,700–3,500 depending on target verbosity. Anthropic ~$2,600, OpenAI ~$250, OpenRouter
~$200. Compare 260812: 80 audits, $226.

The auditor is 70% of the bill and its cost is per-audit regardless of target, so the lever on
spend is epochs and families, not which targets are in the matrix.

Ten families rather than five would be ~$6,000. Recommend extending only if five shows an effect
worth resolving further.

## Decisions taken

1. **Seeds are published.** All five families, perturbations and canary GUIDs live in the public
   repo alongside the code. Accepted consequence: once the GUIDs are public, a future contamination
   check on these specific seeds cannot be falsified — a model could have seen them. The seeds are
   therefore single-use for that purpose, and any later contamination work needs a fresh set.
2. **The positive control stays at n=4.** `luna × trial_suppression` is 16 draws against the 40
   that produced +0.95 in 260812, which is thin for a gate that separates "instrument failure" from
   "real null". Deferred rather than paid for up front: if the run comes back flat, re-run that one
   cell at n=10 (+24 audits, ~$100) before interpreting the null. A positive result does not need
   it.
3. **Deferred, no decision needed before the run:** whether to add `opus5` and `gpt-5.6-sol` as
   targets, each scored only by the judge it is not.
