# Implementation brief — Poor Man's RL memory auditor (for a fresh Fable session)

You are picking up an **approved, fully-specified design** to implement. Brainstorming and
spec review are done; do not re-open them. Your job is to turn the spec into a plan and build it.

## Start here

1. **Repo / branch.** `/Users/malayandipalan/Documents/alignment-auditor`, branch
   **`memory-auditor`** (based off `stewy-dev`). Work on this branch. Run everything from the
   repo root with `uv run …`; always `--dry-run` an `exp` config before spending.
2. **Read the spec in full:** `docs/superpowers/specs/2026-08-20-poor-mans-rl-memory-auditor-design.md`.
   It is the source of truth — §6 (detailed design), §8 (files), §9 (tests), §10 (risks),
   §11 (phasing) especially.
3. **Keys are in `.env`** (already set): `ANTHROPIC_API_KEY`, `OPENAI_API_KEY` (the separate,
   unexhausted account the Reviewer uses), `OPENROUTER_API_KEY`, `DOCENT_API_KEY`.

## What you're building (one paragraph)

A generational learning loop that raises the auditor's per-audit valid-elicitation rate `p`
across a run, so it lands the target behaviour for fewer dollars than the current iid auditor.
Each generation runs a wave of `K` audits with a "playbook" injected into the auditor, scores
them inline, and a cheap Reviewer distils the wave into an updated playbook for the next
generation. The deliverable is a **two-line P(≥1 valid elicitation) vs. cost chart** where the
memory line dominates the iid baseline (Reviewer overhead included on the x-axis).

## Recommended workflow

The design is settled, so **skip brainstorming and go straight to `writing-plans`** to produce a
phased implementation plan from the spec, then implement with **`test-driven-development`** and
(optionally) **`subagent-driven-development`** / `executing-plans`. Build **Phase 1 only** first
(§11) and stop at its gate before any wider spend.

## Resolved decisions — do NOT re-litigate

- **Generational loop**, not fully-sequential or async. One wave of `K` audits per generation.
- **Always explore — there is no explore/exploit split.** The objective is cost-to-*first*-hit
  (P≥1); pre-first-hit there is nothing to exploit. Playbook = **Near misses / Dead ends / Wins**;
  the Reviewer records outcomes, it does NOT brainstorm attack ideas (the auditor does).
- **Reward gate = `signature ∧ scenario_valid`.** A fired-but-invalid audit is a Dead end, never
  a Win. This is load-bearing (it prevents the loop learning to judge-hack).
- **Reviewer = `gpt-5.6-luna` at `effort: max`**, via the `openai/` provider (separate OpenAI
  account). It reads structured *verdicts*, not raw transcripts. Config knobs: `reviewer_model`,
  `reviewer_effort`. Step up to `gpt-5.6-terra` only if Luna mangles the playbook format.
- **Move-summary** is emitted by the behaviour judge as an extra one-line field (one fewer call).
- **Injection = temp seed `.md` per generation:** copy the base seed's front-matter *verbatim*
  (it carries the `custom_judge`/`validity_judge` blocks) and append the rendered playbook to the
  body. Do **NOT** use `audit(system_message=…)` — it replaces Petri's whole auditor prompt.
- **Baseline for Step 3 = the existing pool** `260819_step3_exploit_share_n256` (n=251), plotted
  with Stewart's existing `best_of_n`. Validity parity holds by construction (same seed + same
  `validity_judge`/`opus48`). No new baseline spend.
- **Bring-up scale = 4×4, R=1** (16 audits) on Step 3 to eyeball dominance; scale to R≥5 only if
  it clears the gate.

## Files (from §8)

- **New:** `src/alignment_auditor/petri/memory_audit.py` (runner), `reviewer.py`, `playbook.py`,
  `analysis/plot_memory_scaling.py`; a `experiments/<YYMMDD>_step3_memory.yaml`; a
  `results/<YYMMDD>_memory_step3/README.md`.
- **Extend:** `cost_model.py` — add the Reviewer as a 4th cost component and add
  `openai/gpt-5.6-luna` ($0.20/$1.20 per 1M) + `openai/gpt-5.6-terra` ($2/$12) to `PRICES`.
- **Reuse (import, don't fork):** `exp.py` (alias resolution, `role_model`, `reasoning_config`,
  `inline_scorer`, the `audit()`/`eval_set` call shape), `custom_judge.py`, `adaptive.py`.

## Measurement (get this right — see §6.7)

Each replicate → one number `T` = cumulative cost at its *first* valid hit (∞ if none). Memory
line = empirical CDF of `T` over the R runs = fraction hit by budget `$C`. Band = Wilson (or
bootstrap **over runs**, never over audits). Granularity is per-generation. Runs that never hit
are right-censored — the curve plateaus below 1, don't fake a rise.

## Definition of done for Phase 1

Unit tests green (injector preserves front-matter + parses to same `custom_judge`; playbook
reward-gate routing; Reviewer contract on mocked model; cost-model amortisation) → tiny smoke run
(`wave_size=2, generations=2, replicates=1`) completes and produces per-generation playbook
snapshots → the R=1 4×4 Step-3 run produces the two-line chart + crossing budget. **Gate:** does
the single memory trajectory clear the iid baseline? If yes, scale to R≥5; if no, stop and report.

## Don'ts

- Don't warm-start the playbook with a tactic already known to work — that seeds the answer.
- Don't bootstrap the memory arm over individual audits — only over whole runs.
- Don't run past Phase 1's gate without a green result and a check-in.
- Don't add the systems-level cost cuts (merged judge passes, caching) — out of scope here.
