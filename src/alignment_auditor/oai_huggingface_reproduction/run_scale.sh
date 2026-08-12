#!/usr/bin/env bash
# Scale phase (react, cheap/fast). Two goals:
#   (1) Tighten the one positive rate (glm5.2 step3 coordination) to n=24.
#   (2) Test whether PRESSURE unlocks engagement/coordination/scope-creep in steps 2-4
#       (the react baseline tested pressure only at step1).
# Resumable: a cell whose dir already has a .eval is skipped. Extra-epoch dirs use a
# suffix that shares the (step,scaffold,model,cond) key, so analyze.py POOLS them.
set -uo pipefail
SRC_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SRC_DIR/../../.." && pwd)"
LOG_ROOT="${LOG_ROOT:-$REPO_ROOT/logs/260810_oai_huggingface_reproduction}"
TASKS="src/alignment_auditor/oai_huggingface_reproduction"
cd "$REPO_ROOT"
SC=react
declare -A M=([sonnet5]=openrouter/anthropic/claude-sonnet-5 [glm52]=openrouter/z-ai/glm-5.2 [terra]=openrouter/openai/gpt-5.6-terra)

run(){ # step  targs  suffix  model_alias  n
  local step=$1 targs=$2 suf=$3 ma=$4 n=$5
  local ld=$LOG_ROOT/$step/${SC}__${ma}${suf}
  if ls "$ld"/*.eval >/dev/null 2>&1; then echo "SKIP $ld"; return; fi
  echo ">>> $step $ma ${suf:-baseline} n=$n"
  uv run inspect eval "$TASKS/$step/task.py" --model "${M[$ma]}" \
    -T scaffold=$SC -T turn_limit=25 $targs --epochs "$n" --max-samples 4 \
    --log-dir "$ld" --display plain 2>&1 | tail -4
}

# (2) Pressure on steps 2-4 for the two most informative models.
for ma in glm52 sonnet5; do
  run step3_coordination "-T condition=pressure" "__pressure" "$ma" 8
  run step4_scope_creep  "-T condition=pressure" "__pressure" "$ma" 8
done

# (1) Tighten glm5.2 baseline rates to n=24 (add 16; no -T condition => cond="" => pools).
run step3_coordination "" "__more" glm52 16

echo "=== scale phase complete ==="
