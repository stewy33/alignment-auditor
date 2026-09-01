# Plan: Clean up repo, regenerate results, and complete the blog-post plots

*Session plan — branch `memory-auditor`, drafted 2026-08-31. Rev 3 (addresses @Andy 2nd pass).*

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
(seeds = auditor + judge instructions) — **and rename/reorganize for clarity and consistency**;
(2) write a README (general usage first, then how to recreate each result), pointing at Docent for
transcripts; (3) regenerate clean results where required; (4) complete the analysis and generate
every plot the post needs; **(5) land the finished, cleaned work on `main`, with all results
uploaded to Docent and linked from the README.**

### Repo structure — the organizing principle (@Andy)

One rule settles "what goes in `src/` vs not": **`src/alignment_auditor/` is the installable harness
library — code you import and unit-test. The repo root is the lab notebook that *drives* the library
and *reads its output* — run configs, analysis scripts, results, logs.** So plotting scripts leave
`src/` (they're notebook, not library); the tested, reusable `cost_model.py` stays in the library.

```
src/alignment_auditor/            # LIBRARY: imported + tested
  docker_replication/             # Part 1 harness: env/, harness/, step{1..4} tasks   (was oai_huggingface_reproduction/)
  petri/                          # Parts 2 & 3 harness
    exp.py  custom_judge.py  auditor_tools.py  audit_task.py  canary_check.py  cost_model.py
    seeds/                        # step1_registry_write/  step2_reachout/  step3_exploit_share/  step4_hf_cheat/
    poor_mans_rl/                 # Part 3: memory_audit.py  reviewer.py  playbook.py  adaptive.py
  scripts/                        # smoke_test.py (console entry points)

experiments/                      # LAB NOTEBOOK: run configs, one subdir per part
  part1_docker/                   # the Docker steps' run scripts (Part 1 isn't YAML-driven — it's inspect eval)
  part2_petri/                    # part2_step{1..4}.yaml + part2_step2_iid_baseline.yaml
  part3_poor_mans_rl/             # part3_step2_memory.yaml
analysis/                         # LAB NOTEBOOK: plot scripts (read logs/Docent → figures), import cost_model from the lib
  part1_figures.py  plot_steps_1234.py  plot_cost_scaling.py  plot_step2_memory.py
results/                          # writeups + figures, one subdir per part
logs/                             # raw eval logs (gitignored)
```

This answers all three structure notes: analysis scripts → top-level `analysis/` (run as
`uv run python analysis/<x>.py`); `experiments/` now holds **every** part's run configs (Part 1's
shell runners included), so it's no longer "Petri-only"; `cost_model.py` is the one analysis piece
that stays in `src/` because it's imported by tests and every plotter. *(This is a real move with
import/entry-point churn — flagging it as the one structural decision to confirm before I start.)*

### Naming decisions

- **Seeds → consistent `stepN_` scheme:** `rung1_ladder/L0` → `step1_registry_write/`,
  `step2_reachout_hard` → `step2_reachout/`, `step3_exploit_share/` keeps its name,
  `rung4_hf_cheat` → `step4_hf_cheat/`. **Keep exactly one Step-2 arm** — the static `step2_reachout`
  by default; only keep the `_live` variant instead if Phase 4 shows liveness is what lands the
  result. The "unsolvable-alone / hard" design intent is documented *inside* the seed, not the name.
- **Experiment configs → clear names** (`part2_step1_registry_write.yaml` … `part2_step4_hf_cheat.yaml`,
  `part2_step2_iid_baseline.yaml`, `part3_step2_memory.yaml`), grouped in the per-part subdirs above.
- Renames/moves ripple into imports, `pyproject.toml` entry points, configs, and tests — `uv run
  pytest` is the backstop that catches breakage.

### Model routing (@Andy)

**Standardize on `:nitro` routing for every OpenRouter model** (target, auditor, reviewer, judge) in
the `exp.py` aliases, so `glm52`/`opus48or` resolve to their `:nitro` variants by default. Bonus:
this retires the one unresolved variable from the old "1/128" comparison (nitro-vs-plain routing).

### Key facts established during planning (these drive the whole plan)

- Canonical scenario set is small: the 4 seeds above. Judge rubrics live *inside* each seed's YAML
  front matter (`custom_judge` + `validity_judge` blocks); `custom_judge.py` is a generic runner.
  Everything else is experimental cruft (61 experiment YAMLs, 14 analysis scripts, 11 seed dirs → ~5).
- **Data availability:** Part 1 logs live on **Docent** (S1 `31053a10…` = `oai-hf-step1-fair-cleanenv-glm52-n64`,
  64 runs; S2 `db3e3fd2…` = `oai-hf-step2-reachout-final`, 64 runs — verified accessible, rich
  metadata; S3/S4 URLs pending). Part 2 raw logs are **gone locally → re-run fresh**. Part 3 memory
  logs are **local** (`logs/260824_step2_memory_8x16_withfix/`).
- Access: `.env` has DOCENT/OPENROUTER/ANTHROPIC/OPENAI keys (load with `python-dotenv`, path
  explicit). **No DAYTONA or AWS keys** → Daytona offload and EC2-log recovery are dead; Part 2
  re-runs go local/background (audits are API-bound, not GPU-bound).
- Part 1 harness has a **missing `step1_boundary_probe/` module** (breaks step-2 import + step-1
  elicitation) — recoverable from git commit `517be7e`.

**Sequencing principle:** cheap, local, independent work first (cleanup, README, Part 1 from Docent),
then the one expensive job (Part 2 re-run) which also **produces the clean Step-2 iid baseline that
Part 3 needs**, then the Part 3 figure, then publish + land on main.

---

## Phase 1 — Cut code to the canonical minimum + reorganize

Deletions are safe: git history on this branch preserves everything. Reviewable commits: (a) move
analysis→root & experiments regrouping, (b) rename dirs, (c) seeds, (d) experiments, (e) Part 1,
(f) tests.

**Seeds** (`petri/seeds/`) — keep the 4 canonical (renamed), one Step-2 arm; delete the rest:
- KEEP: `step1_registry_write/`, `step2_reachout/` (single arm), `step3_exploit_share/`,
  `step4_hf_cheat/`, `README.md`.
- DELETE: `rung1/`, `rung1_ladder/{L1,L2,L3,L4}/` + `build_ladder.py`, `rung1_auditor_info/` (all 8),
  the old bare `step2_reachout/`, `step2_reachout_rubric/`, the unused Step-2 arm, `eval_escalation/`,
  `trial_suppression/`.
- Refresh `seeds/README.md` for the current 3-block anatomy (front-matter judge rubrics; AUDITOR
  CALIBRATION / DESIGN PRINCIPLES body; AUDIT MODE) — it predates the custom-judge format.

**Experiments** (`experiments/`, regrouped per part) — 61 YAMLs → keep only what regenerates a result:
- `part2_petri/`: `part2_step{1..4}_*.yaml` + `part2_step2_iid_baseline.yaml` (this **is** the
  "naive scaling" baseline Part 3 compares against).
- `part3_poor_mans_rl/`: `part3_step2_memory.yaml` (from `260824_step2_memory_8x16.yaml`).
- `part1_docker/`: the cleaned per-step run scripts (moved from the Part-1 package).
- DELETE the rest — including the extra iid replicate/live configs (`260828`, `260831`): one clean
  Step-2 iid baseline (Phase 4) is what the post needs.

**Analysis** (new top-level `analysis/`) — keep the blog plotters; `cost_model.py` stays in the lib:
- KEEP/MOVE: `plot_steps_1234.py` (Part 2 elicitation), `plot_cost_scaling.py` (Part 2 cost +
  P-vs-cost). Add `plot_step2_memory.py` (Part 3, Phase 5) and `part1_figures.py` (Phase 3).
- DELETE: `plot_steps_123.py`, `plot_gradient.py`, `plot_detail_ladder.py`, `plot_glm_validity.py`,
  `rate_seed_severity.py`, `stopping_bias.py`, `plot_step2_end_reasons.py`, `plot_step2_turns.py`,
  `plot_step2_hard_turns_hit.py` (diagnostics; not blog figures).

**Part 1** (`docker_replication/`, renamed) — trim to a runnable canonical harness:
- KEEP: `env/`, `harness/`, the 4 step tasks (`step1_gdrive_probe/`, `step2_seeded_probe/`,
  `step3_exploit_share/`, `step4_scope_creep/`), `analyze.py`, `view.py`; run scripts move to
  `experiments/part1_docker/`.
- RESTORE `step1_boundary_probe/` from git (`git show 517be7e:…`) so step-2's import and step-1
  elicitation resolve. (Default: restore — it's the incident-faithful step 1.)
- DELETE: stale multi-cell scripts `run_matrix.sh`, `run_scale.sh`, `run_confirm.sh`,
  `chain_claude_code.sh`, and `daytona_eval.py` (undeclared `daytona` dep, no key).

**Misc:** drop the unused `neutral_restart` preset from `auditor_tools.py`; prune `results/` dirs not
feeding a blog figure (`260805_*`, `260812_seed_gradient`, `260814_detail_ladder`, `260819_steps123`);
keep `tests/` green (update import paths for the moves; 7 files today).

**Verify:** `uv run pytest` green; `uv run exp <each kept config> --dry-run` resolves.

## Phase 2 — README

Rewrite `README.md` in two movements: **(1) general usage** — setup, `.env` (incl. `DOCENT_API_KEY`),
how to run an audit, read results, the repo layout; **(2) recreating the blog** — one short section
per Part with the exact command(s), where results land, and which `analysis/` script draws the figure.
**Point readers to Docent** — one linked collection per part for the transcripts (Part 1 already there;
Part 2/3 uploaded in Phase 6).

## Phase 3 — Part 1 figures (from Docent) — cheap, read-only, independent

Write `analysis/part1_figures.py` that pulls the 4 Docent collections (S1/S2 known; S3/S4 pending)
via the Docent read API (`get_agent_run` / `get_agent_run_metadata`; explicit `.env` path), caches run
metadata + closing text to local JSON under `results/`, and draws:
1. **Elicitation rate per step** — `signature` / `ask_signature` per step, 64 runs each, Wilson CIs.
2. **Signature timing within trajectories** — from `turns` + per-step ordering signals
   (`registry_put_paths`, `n_puts`, …); read transcripts from the agent runs where needed.
3. **Evaluation-awareness** — mine judge rationales / transcripts for eval-awareness cues; if metadata
   lacks a clean signal, run a small **Opus 4.8** judge pass (n=64/step, cheap). **Framing:** report
   this descriptively, not as a caveat that weakens the results — the real OAI/HF agents were
   themselves eval-aware, so eval-awareness is part of the phenomenon, not a threat to it.

Cross-check the Docent-derived rates against `results/260811_oai_huggingface_incident/findings.md` §5.
**Blocked on:** S3/S4 URLs (Steps 1–2 can be built immediately).

## Phase 4 — Part 2 re-run + figures — the expensive job (budget-gated); also produces the iid baseline

1. **Smoke first:** `uv run smoke-test`, then one tiny audit per step (`--dry-run`, then n=1–2) to
   confirm the (now nitro-by-default) routing and that seeds/judges still score.
2. **Re-run the 4 steps** as background, parallel `uv run exp` jobs (per CLAUDE.md), **at one uniform
   n across all four steps** (recommend n=128; confirm at the budget checkpoint). Resumable via
   `eval_set`; report from logs.
3. **Step-2 iid baseline + the "1/128" problem:** the Step-2 automated audit *is* the iid baseline
   Part 3 compares against. Bare iid on `step2_reachout` measured ≈0/1022 before, so a plain run likely
   lands ~0. Recommended: measure first, and if it's 0, apply the **minimal fairness-preserving seed
   tweak** the reviewer discovered — make the blocking artifact one **only a peer can resolve by
   acting** (grant a permission / run a migration), not self-helpable data — to lift Step 2 into a
   low-but-measurable nonzero rate, documenting the change. Fallback: report the measured near-zero
   rate with an upper bound and the "consistent noisy 1/128" framing. **Confirm scale/budget and the
   tweak-vs-measure choice at this checkpoint.**
4. **Regenerate figures:** point `analysis/plot_steps_1234.py` and `analysis/plot_cost_scaling.py` at
   the new log dirs; produce the Part-2 elicitation, cost-per-step, and P-vs-cost figures. Update the
   results README numbers.

## Phase 5 — Part 3 figure (memory arm vs Part-2 iid baseline) — needs Phase 4 done

Write `analysis/plot_step2_memory.py` (the committed version of the ad-hoc `cdf_*.png` work). Memory
arm: `cost_model.load_memory_run("part3_step2_memory")` from local logs (cost-to-first-hit CDF across
5 replicates, right-censored). Baseline: the **clean Step-2 iid results from Phase 4** (not the stale
0/1022), as the naive-scaling line with a Wilson band. Produce the blog's "elicitation rate vs cost —
naive vs Poor-Man's-RL" figure into the Part-3 results `figures/` dir.

## Phase 6 — Publish to Docent + land on main

1. **Upload all runs to Docent** with the `petri-to-docent` skill. Docent **does** support
   multi-agent transcripts: the skill's standard shape is *one AgentRun per audit* whose
   TranscriptGroup already holds separate **auditor**, **target**, and per-**judge** transcripts — so
   Part 2's auditor/target pair is native. For **Part 3's reviewer**, which acts per-*wave* rather than
   per-audit, add the reviewer's per-generation reasoning as its own transcript in the wave's group
   (or a small `reviewer:gen_N` AgentRun) — a minor extension to the standard mapping, called out here
   because the skill defaults to "one AgentRun per audit." Record every collection URL and wire them
   into the README (Phase 2).
2. **Land on `main`.** `memory-auditor` diverged early and lacks Stewy's later Part-1 work now on
   `main`; the cleaned `docker_replication/` overlaps his reproduction dir. Reconcile (merge `main`
   in, resolve the Part-1 overlap in favour of the cleaned tree), open a PR, and merge so the
   finished, deduplicated, fully-reproducible repo is the state of `main`. **Confirm merge strategy
   before pushing.**

## Verification (end-to-end)

- `uv run pytest` green after cleanup + moves.
- Every kept experiment config passes `uv run exp … --dry-run`.
- Each figure regenerates from a single documented command; the README commands reproduce each part.
- Part-1 Docent-derived rates match `findings.md` §5 within sampling noise.
- Part-2 outcomes reported honestly (including a 0 for Step 2 if that's what happens, with the
  framing/tweak decision recorded).
- Docent links resolve; `main` builds, tests pass, and reproduces the post.

## Open dependencies / checkpoints
- **Confirm the `src/` vs root reorganization** (analysis→root, experiments per-part) before I start.
- **S3/S4 Docent URLs** (unblocks Part 1 Steps 3–4 figures).
- **Part 2 budget + infra + uniform-n + Step-2 tweak decision** — confirm before Phase 4 spends money.
- **Merge strategy to land on `main`** — confirm before Phase 6 pushes.
- Suggested execution order: Phase 1 → 2 → 3 (independent, can run alongside) → 4 → 5 → 6.
