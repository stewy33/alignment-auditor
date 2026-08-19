# alignment-auditor — working notes for Claude

## Running experiments / long-running tasks
- **Prefer parallelism.** When you have multiple independent tasks that *can* run at the same time
  — e.g. several `uv run exp <config>` cells, scoring passes, or uploads — launch them as separate
  background processes and run them **in parallel**, not sequentially. Only serialize when there is
  a genuine dependency between steps or a hard resource limit that parallel runs would break.
- Each `uv run exp` cell already runs its own samples concurrently (`max_parallel`), but distinct
  cells/configs are independent and should be started together.
- Use background execution for anything long; report status from the logs rather than blocking.

## Uploading Petri audits to Docent / Transluce
- Use the **petri-to-docent** skill (`.claude/skills/petri-to-docent/SKILL.md`), backed by
  `src/alignment_auditor/petri/docent/petri_to_docent.py`. Standard shape: **one AgentRun per
  audit**, whose **TranscriptGroup holds separate `auditor`, `target`, and one `judge:<label>`
  transcript per judge**, plus flat filterable metadata (rung_level, signature, scenario_valid,
  etc.). Never upload target-only runs for Petri data; don't edit the vendored `docent` plugin skill.
