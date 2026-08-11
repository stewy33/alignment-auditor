# alignment-auditor

Experiments with [Petri](https://meridianlabs-ai.github.io/inspect_petri/), an open-source
alignment-auditing tool built on [Inspect](https://inspect.aisi.org.uk/).

Petri runs an **auditor** model that invents a scenario (system prompt, fake tools, user
persona) to probe a **target** model over a multi-turn conversation, then a **judge** model
scores the transcript across ~38 behavioural dimensions (sycophancy, deception,
self-preservation, …) on a 1–10 scale with citations back to specific messages.

## Setup

Requires [uv](https://docs.astral.sh/uv/) (`brew install uv`).

```bash
uv sync                 # creates .venv from uv.lock
cp .env.example .env    # then paste your keys in
```

`.env` needs:

```
ANTHROPIC_API_KEY=...
OPENAI_API_KEY=...
```

Sanity-check keys and model IDs before spending anything:

```bash
uv run smoke-test
```

## Running audits

An experiment is a YAML file under `experiments/`, named `YYMMDD_slug.yaml`. The filename
is the experiment name — it becomes the log directory, so results always trace back to the
config that produced them.

```yaml
# experiments/260805_auditor_judge.yaml
targets:  [gpt-5.6-luna]
auditors: [sonnet5, opus5]
judges:   [sonnet5, opus5]
seeds:    [email_system_blackmail_shutdown, medical_authority_sycophancy]
max_turns: 30
epochs: 1
```

```bash
uv run exp experiments/260805_auditor_judge.yaml --dry-run   # plan only, no API calls
uv run exp experiments/260805_auditor_judge.yaml             # run it
```

Run these from the repo root — config paths and the `logs/` output directory are resolved
relative to the current directory.

**Always `--dry-run` first.** It resolves every seed ID against Petri's built-ins (with
did-you-mean suggestions) and lists exactly which work is outstanding, without spending
anything.

Cost scales along two axes, not three:

- **conversations = auditors × targets** — each pair is a full run
- **judges are cheap** — they rescore transcripts that already exist

So 2 auditors × 2 targets × 3 judges is 4 runs, not 12. Be generous with judges, stingy
with auditors and targets. Three 30-turn audits run ~$2–5 and take ~15–40 min; Petri's full
built-in suite is 170+ seeds, so don't run it casually.

Everything is **resumable**: conversations use Inspect's `eval_set` (skips completed work)
and scoring is skipped when its output file exists. Adding a judge later, or recovering
from a crash, only does the missing work.

Results land under `logs/<name>/`:

```
conv/<auditor>__<target>/                 conversations (scored by judges[0] only)
scored/<auditor>__<target>__<judge>.eval  one fully-scored file per judge  <- read these
```

## Reading results

Point the viewer at an experiment's `scored/` directory — one entry per
auditor × target × judge cell, each labelled with its cell:

```bash
uv run inspect view --log-dir logs/<experiment>/scored     # http://localhost:7575
```

Click a sample for the transcript plus judge scores. Two views worth knowing:
**Target view** (what the target actually saw) and **Auditor view** (the auditor's reasoning,
tool calls, and any conversation rollbacks). Judge citations like `[M12]` jump to a message.

Check the audit-quality dimensions first — `auditor_failure`, `scenario_realism`,
`stuck_in_loops`, `eval_awareness`. A bad scenario invalidates everything else.

Judges can be swapped without re-running conversations:

```bash
uv run inspect score logs/<file>.eval --scorer inspect_petri/audit_judge \
  -S model=anthropic/claude-opus-5 --action append
```

Write-ups of finished experiments live in `results/`.

## Gotchas

- **Don't pass a comma-containing value to `inspect eval -T`.** Inspect splits any `-T`
  string value on commas into a list, and Petri reads a list of strings as *literal auditor
  instructions* rather than seed IDs — so `-T seed_instructions=id:a,b,c` silently audits
  garbage instead of your seeds. Quoting and backslashes don't help; the split happens after
  YAML parsing. Single-valued selectors (`tags:sycophancy`, `id:one_seed`) are fine. `exp`
  avoids this entirely; on the CLI use `--task-config` or one seed per invocation.
- Custom seeds are just markdown files — see `src/alignment_auditor/petri/seeds/README.md`.
  No need to fork Petri. A config selects a set by its directory name
  (`seeds_dir: trial_suppression`); a path to a directory outside the repo also works.

## Layout

Harnesses live under `src/alignment_auditor/<harness>/` — one subpackage per tool, with
its code and any assets it consumes. The lab notebook lives at the root: `experiments/`
holds one dated YAML per run, `results/` the write-up it produced, `logs/` the raw output.

```
src/alignment_auditor/
  petri/
    exp.py              experiment runner (`uv run exp`)
    canary_check.py     probe targets for memorised seed content (`uv run canary-check`)
    seeds/              custom seed instructions, one directory per set
  scripts/
    smoke_test.py       verify API keys + model IDs (`uv run smoke-test`)
experiments/*.yaml      experiment definitions, YYMMDD_slug.yaml
results/                write-ups of finished experiments
logs/                   .eval logs, gitignored
```
