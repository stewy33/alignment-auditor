# Plan: Clean up repo, regenerate results, and complete the blog-post plots

*Session plan — branch `memory-auditor`, drafted 2026-08-31. Rev 2 (addresses @Andy review).*

## Context

We're releasing a blog post ("Reproducing the OpenAI–Hugging Face Incident…") that reflects the
work in this repo. The post has three technical parts:

- **Part 1 — Manual replication in Docker** (dir → `docker_replication/`): 4 steps, 64 trajectories
  each, GLM 5.2 target / Opus 4.8 judge. Figures: elicitation rate per step, signature timing within
  trajectories, evaluation-awareness.
- **Part 2 — Automated Petri auditing** (`petri/`): elicit each of the 4 steps with a bare auditor.
  Figures: elicitation rate per step, cost per step, P(elicitation) vs cost.
- **Part 3 — Poor-Man's-RL** (`petri/poor_mans_rl/`): a Reviewer proposes strategies each wave;
  demonstrated on Step 2. Figure: elicitation rate vs cost, naive (Part-2 iid) vs Poor-Man's-RL.

The branch (`memory-auditor`) carries our work; Stewy's is on `main`. Five goals this session:
(1) cut the code to the minimum needed to recreate the results — especially the scenario code
(seeds = auditor + judge instructions) — **and rename dirs/files for clarity and consistency**;
(2) write a README that maps each blog part to how to reproduce it, pointing at Docent for
transcripts; (3) regenerate clean results where required; (4) complete the analysis and generate
every plot the post needs; **(5) land the finished, cleaned work on `main`, with all results
uploaded to Docent and linked from the README.**

### Naming & structure (the rename decisions — @Andy)

Three blog parts, but Parts 2 and 3 share the entire Petri harness (`exp.py`, `custom_judge.py`,
seeds, `cost_model.py`), so a hard one-dir-per-part split would duplicate code. Target layout:

```
src/alignment_auditor/
  docker_replication/     Part 1 (renamed from oai_huggingface_reproduction/ — short, matches blog)
  petri/                  Parts 2 & 3 — shared auditing harness
    exp.py, custom_judge.py, auditor_tools.py, audit_task.py, canary_check.py
    seeds/                step1_registry_write/  step2_reachout/ (+ _live)
                          step3_exploit_share/   step4_hf_cheat/
    analysis/             cost_model.py, plot_steps_1234.py, plot_cost_scaling.py,
                          plot_step2_memory.py (Part 3)
    poor_mans_rl/         Part 3 — memory_audit.py, reviewer.py, playbook.py, adaptive.py
```
(@Andy: should plotting scripts be in the src? or in scripts?)

- **Seeds → consistent `stepN_` scheme:** `rung1_ladder/L0` → `step1_registry_write/`,
  `step2_reachout_hard` → `step2_reachout/` (+ `step2_reachout_live/`), `step3_exploit_share/`
  keeps its name, `rung4_hf_cheat` → `step4_hf_cheat/`. The "unsolvable-alone / hard" design intent
  is documented *inside* the seed, not in the dir name.
- **Experiment configs → clear names.** Drop the date-prefix lab-notebook convention for the small
  set of kept blog configs in favour of `part2_step1_registry_write.yaml` … `part2_step4_hf_cheat.yaml`,
  `part2_step2_iid_baseline.yaml`, `part3_step2_memory.yaml`. (Filename still becomes the log-dir
  name; we're regenerating, so this is safe.)
- Renames ripple into imports, `pyproject.toml` entry points, configs, and tests — `uv run pytest`
  is the backstop that catches breakage.

### Key facts established during planning (these drive the whole plan)

- Canonical scenario set is small: the 4 seeds above. Judge rubrics live *inside* each seed's YAML
  front matter (`custom_judge` + `validity_judge` blocks); `custom_judge.py` is a generic runner.
  Everything else is experimental cruft (61 experiment YAMLs, 14 analysis scripts, 11 seed dirs →
  trim to ~5).
- **Data availability:** Part 1 logs live on **Docent** (S1 `31053a10…` = `oai-hf-step1-fair-cleanenv-glm52-n64`,
  64 runs; S2 `db3e3fd2…` = `oai-hf-step2-reachout-final`, 64 runs — both verified accessible with
  rich metadata; S3/S4 URLs pending from you). Part 2 raw logs are **gone locally → re-run fresh**.
  Part 3 memory logs are **local** (`logs/260824_step2_memory_8x16_withfix/`).
- Access: `.env` has DOCENT/OPENROUTER/ANTHROPIC/OPENAI keys (load with `python-dotenv`, path
  explicit). **No DAYTONA or AWS keys** → the Daytona offload and EC2-log-recovery paths are dead;
  Part 2 re-runs go local/background (audits are API-bound, not GPU-bound).
- Part 1 harness has a **missing `step1_boundary_probe/` module** (breaks step-2 import + step-1
  elicitation) — recoverable from git commit `517be7e`.

**Sequencing principle:** cheap, local, independent work first (cleanup, README, Part 1 from Docent),
then the one expensive job (Part 2 re-run) which also **produces the clean Step-2 iid baseline that
Part 3 needs**, then the Part 3 figure, then publish + land on main.

---

## Phase 1 — Cut code to the canonical minimum + rename for clarity

Deletions are safe: git history on this branch preserves everything. Work in a few reviewable
commits (rename, seeds, experiments, analysis, Part 1, tests).

**Seeds** (`petri/seeds/`) — keep the 4 canonical + the live arm (renamed per above); delete the rest:
- KEEP (renamed): `step1_registry_write/`, `step2_reachout/`, `step2_reachout_live/`,
  `step3_exploit_share/`, `step4_hf_cheat/`, `README.md`.
- DELETE: `rung1/`, `rung1_ladder/{L1,L2,L3,L4}/` + `build_ladder.py`, `rung1_auditor_info/` (all 8),
  the old bare `step2_reachout/` and `step2_reachout_rubric/`, `eval_escalation/`, `trial_suppression/`.
- Refresh `seeds/README.md` to document the current 3-block seed anatomy (front-matter judge rubrics;
  AUDITOR CALIBRATION / DESIGN PRINCIPLES body; AUDIT MODE) — it predates the custom-judge format.
(@Andy: we should only keep one step 2 arm - depdning on what we decide to keep at the end.)

**Experiments** (`experiments/`) — 61 YAMLs → keep only what regenerates a blog result (renamed):
- Part 2 (re-run): `part2_step1_registry_write.yaml`, `part2_step2_reachout.yaml`,
  `part2_step3_exploit_share.yaml`, `part2_step4_hf_cheat.yaml`, plus the large-n Step-2 iid baseline
  `part2_step2_iid_baseline.yaml` (this **is** the "naive scaling" baseline Part 3 compares against).
- Part 3: `part3_step2_memory.yaml` (from `260824_step2_memory_8x16.yaml`).
- DELETE the rest — including the extra iid replicate/live configs (`260828`, `260831`): one clean
  Step-2 iid baseline, re-run in Phase 4, is what the post needs.
(@Andy: expeirmets/ only contains petri stuff?)

**Analysis** (`petri/analysis/`) — keep the blog plotters + the shared cost model:
- KEEP: `cost_model.py`, `plot_steps_1234.py` (Part 2 elicitation), `plot_cost_scaling.py` (Part 2
  cost + P-vs-cost). Add `plot_step2_memory.py` (Part 3, Phase 5) and a Part-1 module (Phase 3).
- DELETE: `plot_steps_123.py`, `plot_gradient.py`, `plot_detail_ladder.py`, `plot_glm_validity.py`,
  `rate_seed_severity.py`, `stopping_bias.py`, `plot_step2_end_reasons.py`, `plot_step2_turns.py`,
  `plot_step2_hard_turns_hit.py` (diagnostics; not blog figures).

**Part 1** (`docker_replication/`, renamed) — trim to a runnable canonical harness:
- KEEP: `env/`, `harness/`, the 4 step tasks (`step1_gdrive_probe/`, `step2_seeded_probe/`,
  `step3_exploit_share/`, `step4_scope_creep/`), `analyze.py`, `view.py`, one clean run script per step.
- RESTORE `step1_boundary_probe/` from git (`git show 517be7e:…`) so step-2's import and step-1
  elicitation resolve — or, if we settle on `step1_gdrive_probe` as canonical step 1, delete the
  dangling imports. (Default: restore — it's the incident-faithful step 1.)
- DELETE: stale multi-cell scripts `run_matrix.sh`, `run_scale.sh`, `run_confirm.sh`,
  `chain_claude_code.sh`, and `daytona_eval.py` (undeclared `daytona` dep, no key).

(@Andy: overall the directory structure still feels a bit weird. we should think about what goes in src/ vs not? e.g., analysis v expeimrents)

**Misc:** drop the unused `neutral_restart` preset from `auditor_tools.py`; prune `results/` dirs not
feeding a blog figure (`260805_*`, `260812_seed_gradient`, `260814_detail_ladder`, `260819_steps123`);
remove tests covering deleted code and keep `tests/` green (7 files today).

**Verify:** `uv run pytest` green; `uv run exp <each kept config> --dry-run` resolves.

## Phase 2 — README

Rewrite `README.md` around the three blog parts. For each: what it shows, the canonical
seed(s)/harness, the exact command(s) to reproduce, where results land, and which script draws the
figure. Keep the "Running audits / Reading results / Gotchas" reference sections. **Point readers to
Docent** — one linked collection per part for the transcripts (Part 1 already there; Part 2/3
uploaded in Phase 6) — instead of a local-provenance note. Add the `.env` requirements line
(now including `DOCENT_API_KEY`).

(@Andy: I would suggest the start of the README should focus on general usage / then should go into recreating results.)

## Phase 3 — Part 1 figures (from Docent) — cheap, read-only, independent

Write `docker_replication/part1_figures.py` that pulls the 4 Docent collections (S1/S2 known; S3/S4
pending) via the Docent read API (`get_agent_run` / `get_agent_run_metadata`; load `.env` with an
explicit path), caches run metadata + closing text to local JSON under `results/`, and draws:
1. **Elicitation rate per step** — `signature` / `ask_signature` per step, 64 runs each, Wilson CIs.
2. **Signature timing within trajectories** — from `turns` + per-step ordering signals
   (`registry_put_paths`, `n_puts`, …); where transcripts are needed, read them from the agent runs.
3. **Evaluation-awareness** — mine judge rationales / transcripts for eval-awareness cues; if the
   metadata lacks a clean signal, run a small **Opus 4.8** judge pass over the recovered transcripts
   to score it (n=64/step, cheap). (@Andy: Let's do this but importantly, I think in the real OAI/HF incident, the agents were eval-aware so I'm not sure this should affect our blog results much.)

Cross-check the Docent-derived rates against `results/260811_oai_huggingface_incident/findings.md` §5.
**Blocked on:** S3/S4 URLs from you (Steps 1–2 can be built immediately).

## Phase 4 — Part 2 re-run + figures — the expensive job (budget-gated); also produces the iid baseline

1. **Smoke first:** `uv run smoke-test`, then one tiny audit per step (`--dry-run`, then n=1–2) to
   confirm OpenRouter routing (`glm52` / `opus48ornitro`) and that the seeds/judges still score.
   (@Andy: for all the open-router models, maybe nitro should be default? like we should always use nitro routing?)
2. **Re-run the 4 steps** as background, parallel `uv run exp` jobs (per CLAUDE.md), at the blog's
   n (Step1 64, Step2 128, Step3 256, Step4 128). Resumable via `eval_set`; report from logs. (@Andy: we should run the same n for all!)
3. **Step-2 iid baseline + the "1/128" problem:** the Step-2 automated audit *is* the iid baseline
   Part 3 compares against, so run it at higher n for a tight floor. Bare iid on `step2_reachout`
   measured ≈0/1022 before, so a plain run likely lands ~0. Recommended: measure first, and if it's
   0, apply the **minimal fairness-preserving seed tweak** the reviewer discovered — make the blocking
   artifact one **only a peer can resolve by acting** (grant a permission / run a migration), not
   self-helpable data — to lift Step 2 into a low-but-measurable nonzero rate, documenting the change.
   Fallback: report the measured near-zero rate with an upper bound and the "consistent noisy 1/128"
   framing. **Confirm scale/budget and the tweak-vs-measure choice at this checkpoint.**
4. **Regenerate figures:** point `plot_steps_1234.py` and `plot_cost_scaling.py` at the new log dirs;
   produce the Part-2 elicitation, cost-per-step, and P-vs-cost figures. Update the results README numbers.

## Phase 5 — Part 3 figure (memory arm vs Part-2 iid baseline) — needs Phase 4 done

Write `petri/analysis/plot_step2_memory.py` (the committed version of the ad-hoc `cdf_*.png` work).
Memory arm: `cost_model.load_memory_run("part3_step2_memory")` from the local logs (cost-to-first-hit
CDF across 5 replicates, right-censored). Baseline: the **clean Step-2 iid results from Phase 4** (not
the stale 0/1022), plotted as the naive-scaling line with a Wilson band. Produce the blog's
"elicitation rate vs cost — naive vs Poor-Man's-RL" figure into the Part-3 results `figures/` dir.

## Phase 6 — Publish to Docent + land on main

1. **Upload all runs to Docent** with the repo's `petri-to-docent` skill (one AgentRun per audit;
   auditor/target/judge transcripts). Part 1 is already there (S1–S4); upload the fresh Part 2 and
   Part 3 runs and record the collection URLs. Wire those links into the README (Phase 2).
   (@Andy: one note, does Docent support multi-agent transcripts? FOr Part 2, there's auditor / target. And how would we uplaod reviewer transcript fr Part 3?)
2. **Land on `main`.** `memory-auditor` diverged early and lacks Stewy's later Part-1 work now on
   `main`; the cleaned `docker_replication/` overlaps his reproduction dir. Reconcile (merge `main`
   in, resolve the Part-1 overlap in favour of the cleaned tree), open a PR, and merge so the
   finished, deduplicated, fully-reproducible repo is the state of `main`. **Confirm the merge
   strategy with you before pushing.**

## Verification (end-to-end)

- `uv run pytest` green after cleanup + renames.
- Every kept experiment config passes `uv run exp … --dry-run`.
- Each figure regenerates from a single documented command (Part 1 Docent pull, Part 2 post-rerun,
  Part 3 local + Phase-4 baseline), and the README commands reproduce each part.
- Part-1 Docent-derived rates match `findings.md` §5 within sampling noise.
- Part-2 outcomes reported honestly (including a 0 for Step 2 if that's what happens, with the
  framing/tweak decision recorded).
- Docent links resolve; `main` builds, tests pass, and reproduces the post.

## Open dependencies / checkpoints
- **S3/S4 Docent URLs** from you (unblocks Part 1 Steps 3–4 figures).
- **Part 2 budget + infra + Step-2 tweak decision** — confirm before Phase 4 spends real money.
- **Merge strategy to land on `main`** — confirm before Phase 6 pushes.
- Suggested execution order: Phase 1 → 2 → 3 (independent, can run alongside) → 4 → 5 → 6.
