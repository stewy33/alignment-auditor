# alignment-auditor — working notes for Claude

## Running experiments / long-running tasks
- **Prefer parallelism.** When you have multiple independent tasks that *can* run at the same time
  — e.g. several `uv run exp <config>` cells, scoring passes, or uploads — launch them as separate
  background processes and run them **in parallel**, not sequentially. Only serialize when there is
  a genuine dependency between steps or a hard resource limit that parallel runs would break.
- Each `uv run exp` cell already runs its own samples concurrently (`max_parallel`), but distinct
  cells/configs are independent and should be started together.
- Use background execution for anything long; report status from the logs rather than blocking.
