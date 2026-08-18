#!/usr/bin/env bash
# Drive the 10-cell detail-ablation ladder: 2 auditor arms x 5 detail levels.
#
# Sequential on purpose. Each cell already runs 16 audits concurrently (max_parallel: 16);
# running cells in parallel too would put 160 audits in flight against OpenRouter and turn
# rate-limiting into a confound that lands unevenly across the ladder.
#
# `|| true` per cell: a cell that dies (provider error, auth, a weak auditor that cannot drive
# the harness at all) must not take the remaining cells with it -- partial ladder data is still
# worth having, and the plot script reports whatever cells produced logs.
#
# Resume is native: re-running this script skips audits already on disk, so an interrupted run
# can simply be re-launched.
set -u
cd "$(dirname "$0")/.."

for CFG in \
  experiments/260814_ladder_glm52_L0.yaml \
  experiments/260814_ladder_glm52_L1.yaml \
  experiments/260814_ladder_glm52_L2.yaml \
  experiments/260814_ladder_glm52_L3.yaml \
  experiments/260814_ladder_glm52_L4.yaml \
  experiments/260814_ladder_dsv4flash_L0.yaml \
  experiments/260814_ladder_dsv4flash_L1.yaml \
  experiments/260814_ladder_dsv4flash_L2.yaml \
  experiments/260814_ladder_dsv4flash_L3.yaml \
  experiments/260814_ladder_dsv4flash_L4.yaml
do
  echo "=============================================================="
  echo "=== START $(basename "$CFG")  $(date -Is)"
  echo "=============================================================="
  uv run python -m alignment_auditor.petri.exp "$CFG" || true
  echo "=== DONE  $(basename "$CFG")  $(date -Is)"
done

echo "=== LADDER COMPLETE $(date -Is)"
