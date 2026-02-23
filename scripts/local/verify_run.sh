#!/usr/bin/env bash
set -euo pipefail

pytest -q

set -a
source .env
set +a

RUN_ID="thesis_improved_$(date +%Y%m%d_%H%M%S)"
echo "RUN_ID=$RUN_ID"

fagan run --config configs/examples/c1_ubr.yaml --run-id "$RUN_ID"
fagan eval --run "$RUN_ID" --gold artifacts/gold/Faults_List_In_ver6.xls --match-threshold 0.65

echo "== runs/$RUN_ID =="; ls -lah "runs/$RUN_ID"
echo "== eval/$RUN_ID =="; ls -lah "eval/$RUN_ID"
