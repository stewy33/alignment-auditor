#!/usr/bin/env bash
set -uo pipefail
cd /mnt/HC_Volume_106513277/alignment-auditor
for lv in L0 L1 L2 L3; do
  echo "===== $(date +%H:%M:%S) RUN 260815_rubsub_$lv (rubric+submit) ====="
  uv run exp experiments/260815_rubsub_$lv.yaml || echo "!! $lv nonzero"
done
echo "===== $(date +%H:%M:%S) ALL rubsub CELLS DONE ====="
