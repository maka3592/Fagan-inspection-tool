#!/usr/bin/env bash
set -euo pipefail

RUN_ID="${1:?usage: ./eval_thresholds.sh <run_id>}"
GOLD="${2:-artifacts/gold/Faults_List_In_ver6.xls}"

for T in 0.60 0.65 0.70; do
  echo "=== Evaluating $RUN_ID @ threshold $T ==="
  fagan eval --run "$RUN_ID" --gold "$GOLD" --match-threshold "$T"
  THR=$(python - <<PY
t="$T"
print(f"thr{int(round(float(t)*100)):03d}")
PY
)
  cp -R "eval/$RUN_ID" "eval/${RUN_ID}_${THR}"
done

echo "Done:"
ls -1 eval | grep "${RUN_ID}_thr" || true
