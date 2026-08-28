#!/usr/bin/env bash
# Re-run the glm52 detail ladder with the NEW judges (behaviour trimmed; validity + UNSANCTIONED)
# and adaptive early stopping at 3 successes. Sequential; each cell already runs 16 in parallel.
set -uo pipefail
cd /mnt/HC_Volume_106513277/alignment-auditor
for lv in L0 L1 L2 L3 L4; do
  echo "===== $(date +%H:%M:%S)  RUN 260815_ladder_glm52_$lv ====="
  uv run exp experiments/260815_ladder_glm52_$lv.yaml || echo "!! $lv exited nonzero"
done
echo "===== $(date +%H:%M:%S)  ALL CELLS DONE ====="
