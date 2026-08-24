# Memory-auditor ("Poor Man's RL") — handoff note

**Date:** 2026-08-24  ·  **Branch:** `memory-auditor`
**Read first:** the design spec `2026-08-20-poor-mans-rl-memory-auditor-design.md` (unchanged; still
the source of truth for the mechanism).

## TL;DR of where we left it

The system is **built and unit-tested (43 tests green)**. The generational memory loop **works
end-to-end on Step 3**. It is **not yet shown to *raise* the elicitation rate** (a "memory effect"),
because the two steps we tried are each a poor fit for the demo, for opposite reasons. Nothing is
running; all cloud resources are torn down.

## What's built (all on this branch, committed)

- `petri/playbook.py` — playbook data model + the **reward-gate classifier** (`classify`: signature∧valid→Win,
  fired-but-invalid→Dead-end, valid-but-partial→Near-miss) + the seed **injector** (`compose_seed`,
  preserves front matter byte-for-byte).
- `petri/reviewer.py` — the Luna reviewer: distils a wave's verdicts into the next playbook; gate is
  code-enforced (LLM can't invent wins); deterministic fallback if the model output is unparseable.
- `petri/memory_audit.py` — the generational runner: injects → runs a wave (`eval_set`) → inline
  scores → reviews. Resume-safe (per-gen snapshots + `done.json`). Knobs: `stop_at_first_hit` (default
  on), `--only-rep N` (run one replicate as its own process, for parallelism).
- `petri/exp.py` — added `openrouter_provider` routing (glm auditor+target only) + `--only-rep` +
  `build_audit_task`.
- `petri/analysis/cost_model.py` — reviewer as a 4th cost component; Novita/Luna/Terra prices;
  `load_memory_run`.
- `petri/analysis/plot_memory_scaling.py` — the two-line P(≥1 valid)-vs-cost chart (CDF of cost-to-first-hit).
- `tests/` — 43 tests (gate routing, injector round-trip, reviewer contract, cost amortisation,
  stop-at-first-hit, provider routing, plot accounting).

Run: `uv run exp experiments/<cfg>.yaml [--dry-run] [--only-rep N]` ·
plot: `python -m alignment_auditor.petri.analysis.plot_memory_scaling --run <logdir>`.

## What's proven — Step 3

Pipeline works: `results/260821_memory_step3/` has the deliverable. R=1 (local 4×4) gave a clean
two-line chart (cost-to-first-hit T=$4.09). The cloud R=8 run landed **6 valid hits across 5/8
replicates** before it was stopped.
**Caveat / why it doesn't show a memory *effect*:** at Step 3's ~0.23 hit rate, the first hit lands
in **generation 0** — which uses an empty playbook and *is* the baseline auditor. So the win happens
before any learning, and the memory mechanism never gets to act. Step 3 proves the machinery, not the
hypothesis.

## What failed — Step 2 (and exactly why)

Two runs (`260821_step2_memory.yaml` 40-concurrent, then `260822_step2_memory.yaml` 80-concurrent,
Novita-pinned) → **0 generations completed in ~14 h, ~$738 spent, 0 hits.** The memory loop never
iterated once. Root cause, fully diagnosed:
- Step-2 audits (`step2_reachout_hard`, impossible task + exhaust-every-affordance persona) run the
  **full 60 turns** — the target never submits early → maximally long audits (**~1.5–2.5 h each** under
  load; Step 3 audits were ~20 min).
- Concurrency is **connection-limited to ~13/16** per process, so ~3 audits per wave start late; a
  generation only closes when its **slowest** audit finishes → **~6–11 h per generation** → multi-day run.
- Higher concurrency (the 2× attempt) made it *worse* (bigger waves = more stragglers). **Audit length,
  not concurrency, is the wall.**
- Also: 1/127 hit rate means ~100+ audits/replicate before a hit even becomes likely.

## The open goal + recommended next steps

**Goal still open:** demonstrate that memory *raises* p (the memory line left-shifts vs the iid
baseline). Neither step delivered it — Step 3 hits too early (pre-learning), Step 2 too slow/rare.

Options, best-first:
1. **Moderately-hard target** (recommended): a tuned Step-3-like seed where audits **conclude fast**
   (target submits, ~20 min) AND the rate is **moderate** (~0.05–0.15, so gen 0 usually *misses* and
   later generations can act). This is the design's real sweet spot and is cheap to iterate.
2. **Step 2 with `max_turns` 30** (salvage): directly cuts audit length. Validity check first — see if
   reach-outs happen before turn 30 (`analysis/plot_step2_hard_turns_hit.py`; baseline pool
   `260821_step2_hard_n128`).
3. Accept Step 3 + the built machinery as the deliverable and write it up.

## Gotchas for whoever picks this up

- **iCloud evicts `.venv`** → `uv run`/imports hang forever. Fix: external venv, e.g.
  `UV_PROJECT_ENVIRONMENT=~/.venvs/aa uv sync` then `PYTHONPATH=<repo>/src uv run --no-sync ...`.
  (memory: `venv-icloud-eviction`.)
- **glm/OpenRouter throughput** ~1 audit/min, degrades under concurrency; default routing collapses.
  **Pin Novita (fp8)** via `openrouter_provider: {order: [novita], allow_fallbacks: true}` — measured
  best fp8 provider; ~9.5 req/s ceiling at 80 concurrent. Don't fan out many competing processes.
  (memory: `glm-openrouter-throughput`.)
- **Routing**: Anthropic via OpenRouter (`opus48or`; the direct account is spend-capped), OpenAI direct
  (`gpt-5.6-luna` reviewer). (memory: `model-provider-routing`.)
- **Baseline pool logs** (`260819_step3_exploit_share_n256`, `260821_step2_hard_n128`) are **not on this
  machine** → the chart uses a labelled stand-in baseline. Restore the logs to get the real bootstrap.
- **Cost model** prices glm at the Z.AI rate ($1.4/$4.4) for both arms (fair comparison); **actual**
  Novita spend is ~half — so the OpenRouter bill runs under the chart's implied cost.
- **Cloud recipe** (if re-running): r7g.xlarge (32 GB) in us-east-1, ~$0.21/h; SSH SG locked to your IP;
  `--only-rep` processes; a box-side `cap_monitor.sh` polling OpenRouter to self-enforce a spend cap.
  ALWAYS terminate the box + delete SG/keypair when done.

## Spend on this exploration
Step 3 ~$40 + Step 2 ~$738 (no usable result) + AWS ~$4.35 ≈ **~$782**, all OpenRouter/EC2, under caps.
