#!/usr/bin/env bash
# Run the incident matrix for one scaffold across all steps and the three target models.
#
#   incidents/run_matrix.sh <scaffold> <n_epochs> [turn_limit]
#
# Resumable: a cell whose log dir already holds a .eval is skipped. Each cell logs to
# incidents/<stepdir>/logs/<scaffold>__<model>[__<condition>]/.
set -uo pipefail
cd "$(dirname "$0")/.."   # repo root

SCAFFOLD="${1:?usage: run_matrix.sh <scaffold> <n> [turn_limit]}"
N="${2:?usage: run_matrix.sh <scaffold> <n> [turn_limit]}"
TURNS="${3:-}"
if [ -z "$TURNS" ]; then
  case "$SCAFFOLD" in react) TURNS=25;; *) TURNS=40;; esac
fi

# model alias -> OpenRouter id
declare -A MODELS=(
  [sonnet5]="openrouter/anthropic/claude-sonnet-5"
  [glm52]="openrouter/z-ai/glm-5.2"
  [terra]="openrouter/openai/gpt-5.6-terra"
)

# step dir : task file : extra -T args (space separated) : log suffix
# step1 has two conditions; steps 2-4 have one.
run_cell () {
  local stepdir="$1" targs="$2" suffix="$3" model_alias="$4"
  local model="${MODELS[$model_alias]}"
  local logdir="incidents/${stepdir}/logs/${SCAFFOLD}__${model_alias}${suffix}"
  if ls "${logdir}"/*.eval >/dev/null 2>&1; then
    echo "SKIP (exists): ${logdir}"
    return
  fi
  echo ">>> RUN ${stepdir} ${SCAFFOLD} ${model_alias} ${suffix:-} (n=${N}, turns=${TURNS})"
  uv run inspect eval "incidents/${stepdir}/task.py" \
    --model "$model" \
    -T scaffold="$SCAFFOLD" -T turn_limit="$TURNS" $targs \
    --epochs "$N" --max-samples 8 \
    --log-dir "$logdir" --display plain 2>&1 | tail -6
}

for m in sonnet5 glm52 terra; do
  run_cell step1_boundary_probe "-T condition=baseline" "__baseline" "$m"
  run_cell step1_boundary_probe "-T condition=pressure" "__pressure" "$m"
  run_cell step2_engagement    "" "" "$m"
  run_cell step3_coordination  "" "" "$m"
  run_cell step4_scope_creep   "" "" "$m"
done
echo "=== matrix complete for scaffold=${SCAFFOLD} ==="
