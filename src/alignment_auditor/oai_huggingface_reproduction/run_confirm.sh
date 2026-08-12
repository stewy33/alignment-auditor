#!/usr/bin/env bash
# Confirmation phase (react): strengthen the two claims that most need N.
#   - step4 "stops" is the key SAFETY claim -> push glm5.2 step4 to n=32 per condition.
#   - glm5.2 step2/step3 PRESSURE were only n=8 -> add 16 to reach n=24.
# Extra-epoch dirs share the (step,scaffold,model,cond) key, so analyze.py pools them.
set -uo pipefail
SRC_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SRC_DIR/../../.." && pwd)"
LOG_ROOT="${LOG_ROOT:-$REPO_ROOT/logs/260810_oai_huggingface_reproduction}"
TASKS="src/alignment_auditor/oai_huggingface_reproduction"
cd "$REPO_ROOT"
SC=react
declare -A M=([glm52]=openrouter/z-ai/glm-5.2 [sonnet5]=openrouter/anthropic/claude-sonnet-5)

run(){ # step targs suffix model n
  local step=$1 targs=$2 suf=$3 ma=$4 n=$5
  local ld=$LOG_ROOT/$step/${SC}__${ma}${suf}
  if ls "$ld"/*.eval >/dev/null 2>&1; then echo "SKIP $ld"; return; fi
  echo ">>> $step $ma $suf n=$n"
  uv run inspect eval "$TASKS/$step/task.py" --model "${M[$ma]}" \
    -T scaffold=$SC -T turn_limit=25 $targs --epochs "$n" --max-samples 6 \
    --log-dir "$ld" --display plain 2>&1 | tail -4
}

# Strengthen the safety claim: glm step4 to n=32 per condition (add 24 to the n=8 cells).
run step4_scope_creep "-T condition=baseline" "__moreA" glm52 24
run step4_scope_creep "-T condition=pressure" "__pressA" glm52 24
# Confirm sonnet also holds at higher N (add 16 baseline).
run step4_scope_creep "-T condition=baseline" "__moreA" sonnet5 16
# Tighten the noisy pressure engagement/coordination cells to n=24.
run step3_coordination "-T condition=pressure" "__pressA" glm52 16
echo "=== confirm phase complete ==="
