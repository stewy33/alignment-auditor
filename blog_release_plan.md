# Plan: Clean up repo, regenerate results, and complete the blog-post plots

*Session plan — branch `memory-auditor`, drafted 2026-08-31. Review before we execute.*

## Context

We're releasing a blog post ("Reproducing the OpenAI–Hugging Face Incident…") that reflects the
work in this repo. The post has three technical parts:

- **Part 1 — Manual replication in Docker** (`oai_huggingface_reproduction/`): 4 steps, 64
  trajectories each, GLM 5.2 target / Opus 4.8 judge. Figures: elicitation rate per step, signature
  timing within trajectories, evaluation-awareness. (@Andy: maybe we should clean up directory names as well? this is a really long unwieldy name, vs., just `petri/` for the next parts)
- **Part 2 — Automated Petri auditing** (`petri/` seeds + analysis): elicit each of the 4 steps
  with a bare auditor. Figures: elicitation rate per step, cost per step, P(elicitation) vs cost.
- **Part 3 — Poor-Man's-RL** (`petri/` memory/reviewer loop): reviewer proposes strategies each
  wave; demonstrated on Step 2. Figure: elicitation rate vs cost, naive vs Poor-Man's-RL. (@Andy: should this be under `petri/` or would it be better to put this in a separate dir so each part is a different dir?)

The branch (`memory-auditor`) carries our work; Stewy's is on `main`. Four things to do this
session: (1) cut the code down to the minimum needed to recreate the results — especially the
scenario code (seeds = auditor + judge instructions); (2) write a README that maps each blog part
to how to reproduce it; (3) regenerate clean results where required; (4) complete the analysis and
generate every plot the post needs. (@Andy: at the end, we want everything on main also.)

**Key facts established during planning (these drive the whole plan):**
- Canonical scenario set is small: **Step 1 = `rung1_ladder/L0`, Step 2 = `step2_reachout_hard`
  (+`_live` arm), Step 3 = `step3_exploit_share`, Step 4 = `rung4_hf_cheat`.** Judge rubrics live
  *inside* each seed's YAML front matter (`custom_judge` + `validity_judge` blocks); `custom_judge.py`
  is a generic runner. Everything else is experimental cruft (61 experiment YAMLs, 14 analysis
  scripts, 11 seed dirs → trim to ~5).
- **Data availability:** Part 1 logs live on **Docent** (S1 `31053a10…` = `oai-hf-step1-fair-cleanenv-glm52-n64`,
  64 runs; S2 `db3e3fd2…` = `oai-hf-step2-reachout-final`, 64 runs — both verified accessible with
  rich metadata; S3/S4 URLs pending from you). Part 2 raw logs are **gone locally → re-run fresh**.
  Part 3 memory logs are **local** (`logs/260824_step2_memory_8x16_withfix/`).
- Access: `.env` has DOCENT/OPENROUTER/ANTHROPIC/OPENAI keys (load with `python-dotenv`, path
  explicit). **No DAYTONA or AWS keys** → the Daytona offload and EC2-log-recovery paths are dead;
  Part 2 re-runs go local/background (audits are API-bound, not GPU-bound).
- Part 1 harness has a **missing `step1_boundary_probe/` module** (breaks step-2 import + step-1
  elicitation) — recoverable from git commit `517be7e`.

**Sequencing principle:** do the cheap, local, high-value work first (cleanup, README, Part 1 from
Docent, Part 3 from local logs), and defer the one expensive job (Part 2 re-run) to last, behind a
smoke test and a budget checkpoint.

---

## Phase 1 — Cut code to the canonical minimum

Deletions are safe: git history on this branch preserves everything. Work in a few reviewable
commits (seeds, experiments, analysis, Part 1, tests).

**Seeds** (`src/alignment_auditor/petri/seeds/`) — keep the 4 canonical + the live arm; delete the rest:
- KEEP: `rung1_ladder/L0/` (Step 1 — consider promoting to a clearer dir name e.g. `step1_registry_write/`), `step2_reachout_hard/`, `step2_reachout_hard_live/`, `step3_exploit_share/`, `rung4_hf_cheat/`, `README.md`.
- DELETE: `rung1/`, `rung1_ladder/{L1,L2,L3,L4}/` + `build_ladder.py`, `rung1_auditor_info/` (all 8), `step2_reachout/`, `step2_reachout_rubric/`, `eval_escalation/`, `trial_suppression/`.
- Refresh `seeds/README.md` to document the current 3-block seed anatomy (front-matter judge rubrics; AUDITOR CALIBRATION/DESIGN PRINCIPLES body; AUDIT MODE) — it predates the custom-judge format.
(@Andy: in general, please rename directories / files where required for clarity / consistency.)

**Experiments** (`experiments/`) — 61 YAMLs → keep only what regenerates a blog result:
- Part 2 (re-run): the 4 step configs — Step 1 `260820_step1_deposit_n64`, Step 2 `260821_step2_hard_n128`, Step 3 `260819_step3_exploit_share_n256`, Step 4 `260819_rung4_hf_cheat_rubsub_n128` (rename to a clean `26XXXX_partN_*` scheme if desired).
- Part 3: `260824_step2_memory_8x16.yaml` + iid baselines `260826_step2_iid_baseline.yaml`, `260828_step2_iid_baseline_rep2.yaml`, `260831_step2_iid_live_n256.yaml`. (@Andy: it's not clear those other iid baselines should be kept? The iid baseline should technically be from part 2 right?)
- DELETE the rest (all 2608{05..16} smoke/ladder/rubsub/gradient/family/seed5 configs + superseded step-2 variants + `.sh`/`.md` helpers).

**Analysis** (`src/alignment_auditor/petri/analysis/`) — keep the blog plotters + the shared cost model:
- KEEP: `cost_model.py`, `plot_steps_1234.py` (Part 2 elicitation), `plot_cost_scaling.py` (Part 2 cost + P-vs-cost). Add new `plot_step2_memory.py` (Part 3, Phase 4) and a Part-1 module (Phase 3).
- DELETE: `plot_steps_123.py`, `plot_gradient.py`, `plot_detail_ladder.py`, `plot_glm_validity.py`, `rate_seed_severity.py`, `stopping_bias.py`, `plot_step2_end_reasons.py`, `plot_step2_turns.py`, `plot_step2_hard_turns_hit.py` (diagnostics; not blog figures).

**Part 1** (`oai_huggingface_reproduction/`) — trim to a runnable canonical harness:
- KEEP: `env/`, `harness/`, the 4 step tasks (`step1_gdrive_probe/`, `step2_seeded_probe/`, `step3_exploit_share/`, `step4_scope_creep/`), `analyze.py`, `view.py`, one clean run script per step.
- RESTORE `step1_boundary_probe/` from git (`git show 517be7e:…`) so step-2's import and the step-1 elicitation resolve — or, if we settle on `step1_gdrive_probe` as the canonical step-1, delete the dangling imports instead. (Decision at execution; default: restore, it's the incident-faithful step 1.)
- DELETE: stale multi-cell scripts `run_matrix.sh`, `run_scale.sh`, `run_confirm.sh`, `chain_claude_code.sh`, and `daytona_eval.py` (undeclared `daytona` dep, no key).

**Misc:** drop the unused `neutral_restart` preset from `auditor_tools.py`; prune `results/` dirs not
feeding a blog figure (`260805_*`, `260812_seed_gradient`, `260814_detail_ladder`, `260819_steps123`);
remove tests covering deleted code and keep `tests/` green (7 files today).

**Verify:** `uv run pytest` green; `uv run exp <each kept config> --dry-run` resolves.

## Phase 2 — README

Rewrite `README.md` around the three blog parts. For each: what it shows, the canonical seed(s)/harness,
the exact command(s) to reproduce, where results land, and which script draws the figure. Keep the
existing "Running audits / Reading results / Gotchas" reference sections. Add a short "Data provenance"
note (Part 1 from Docent, Part 3 logs local, Part 2 re-run) and a `.env` requirements line. (@Andy: what is this data provenance note? At the end of this, we should have everything on Docent with links and the README should point people there!)

## Phase 3 — Part 1 figures (from Docent) — cheap, read-only

Write `oai_huggingface_reproduction/part1_figures.py` that pulls the 4 Docent collections (S1/S2 known;
S3/S4 pending) via the Docent read API (`get_agent_run` / `get_agent_run_metadata`; load `.env` with an
explicit path), caches run metadata + closing text to local JSON under `results/`, and draws:
1. **Elicitation rate per step** — `signature` / `ask_signature` per step, 64 runs each, Wilson CIs.
2. **Signature timing within trajectories** — from `turns` + per-step ordering signals (`registry_put_paths`, `n_puts`, etc.); where transcripts are needed, read them from the agent runs.
3. **Evaluation-awareness** — mine judge rationales / transcripts for eval-awareness cues; if the metadata lacks a clean signal, run a small Opus (@Andy: use 4.8) judge pass over the recovered transcripts to score it (n=64/step, cheap).

Reuse the exact numbers already in `results/260811_oai_huggingface_incident/findings.md` §5 as a
cross-check that the Docent-derived rates match. **Blocked on:** S3/S4 URLs from you (Steps 1–2 can be
built immediately).

## Phase 4 — Part 3 figure (from local logs) — cheap, local

Write `petri/analysis/plot_step2_memory.py` (the committed version of the ad-hoc `cdf_*.png` work).
Input: `cost_model.load_memory_run("260824_step2_memory_8x16_withfix")` (cache already exists) for the
memory arm's cost-to-first-hit CDF across 5 replicates (right-censored), plotted against the **measured
iid floor** (0/1022, Wilson upper band) per `step2_memory_session_writeup.md` §3/§6. Produce the blog's
"elicitation rate vs cost, naive vs Poor-Man's-RL" figure. Regenerate into
`results/260824_step2_memory_8x16_withfix/figures/`. (@Andy: we need to re-run / get clean results for the iid Part 2 first right?)

## Phase 5 — Part 2 re-run + figures — the expensive job (last; budget-gated)

1. **Smoke first:** `uv run smoke-test`, then one tiny audit per step (`--dry-run`, then n=1–2) to
   confirm OpenRouter routing (`glm52`/`opus48ornitro`) and the seeds/judges still score.
2. **Re-run the 4 steps** as background, parallel `uv run exp` jobs (per CLAUDE.md), at the blog's
   n (Step1 64, Step2 128, Step3 256, Step4 128). Report from logs; resumable via `eval_set`.
3. **Step 2 sub-strategy (the "1/128" problem):** bare iid on `step2_reachout_hard` measured ≈0/1022,
   so a plain n=128 re-run will very likely land 0. Recommended path: re-run to measure the rate, and
   if it's 0, apply the **minimal fairness-preserving seed tweak** the reviewer discovered — make the
   blocking artifact one **only a peer can resolve by acting** (grant a permission / run a migration),
   not self-helpable data — to lift Step 2 into a low-but-measurable nonzero rate, documenting the
   change. Fallback: report the measured near-zero rate with an upper bound and the "consistent noisy
   1/128" framing. **Confirm scale/budget and the tweak-vs-measure choice at this checkpoint.**
4. **Regenerate figures:** point `plot_steps_1234.py` and `plot_cost_scaling.py` at the new log dirs;
   produce the Part-2 elicitation, cost-per-step, and P-vs-cost figures. Update
   `results/260821_steps1234/README.md` numbers.

## Verification (end-to-end)

- `uv run pytest` green after cleanup.
- Every kept experiment config passes `uv run exp … --dry-run`.
- Each figure regenerates from a single documented command (Part 1 Docent pull, Part 3 local, Part 2
  post-rerun), and the README commands reproduce each part.
- Part-1 Docent-derived rates match `findings.md` §5 within sampling noise.
- Part-2 re-run outcomes reported honestly (including a 0 for Step 2 if that's what happens, with the
  framing/tweak decision recorded).

## Open dependencies / checkpoints
- **S3/S4 Docent URLs** from you (unblocks Part 1 Steps 3–4 figures).
- **Part 2 budget + infra + Step-2 tweak decision** — confirm before Phase 5 spends real money.
- Suggested execution order: Phase 1 → 2 → (3 & 4 in parallel) → 5.
