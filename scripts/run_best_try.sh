#!/usr/bin/env bash
# run_best_try.sh — Run C1_UBR inspection with per-reviewer focus + evaluate
#
# Features used:
#   - Per-reviewer focus partitioning (reviewer_focus in config)
#   - Gold-aligned description prompt (reviewer_ubr.txt v2)
#   - Dedup rescue (programmatic consolidation protection)
#   - Canonical position tokens (strict matching)
#
# Usage:
#   ./scripts/run_best_try.sh [RUN_ID]
#
# Examples:
#   ./scripts/run_best_try.sh                    # auto-generates ID
#   ./scripts/run_best_try.sh my_experiment_001  # custom ID

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_DIR"

RUN_ID="${1:-thesis_best_try}"
CONFIG="configs/examples/c1_ubr.yaml"
GOLD="artifacts/gold/Faults_List_In_ver6.xls"

echo "=== Fagan C1_UBR Best-Try Run ==="
echo "Config:  $CONFIG"
echo "Run ID:  $RUN_ID"
echo "Gold:    $GOLD"
echo ""

# Step 1: Run inspection
echo "--- Step 1: Running inspection ---"
fagan run --config "$CONFIG" --run-id "$RUN_ID"
echo ""

# Step 2: Evaluate against gold standard
echo "--- Step 2: Evaluating against gold standard ---"
fagan eval --run "$RUN_ID" --gold "$GOLD"
echo ""

# Step 3: Show key metrics
METRICS_FILE="eval/$RUN_ID/metrics.json"
if [ -f "$METRICS_FILE" ]; then
    echo "--- Results ---"
    python3 -c "
import json, sys
with open('$METRICS_FILE') as f:
    m = json.load(f)
print(f'  True Positives:  {m[\"true_positives\"]} (exact={m.get(\"true_positives_exact\",0)}, partial={m.get(\"true_positives_partial\",0)})')
print(f'  False Positives: {m[\"false_positives\"]} (in-scope={m.get(\"false_positives_in_scope\",0)}, out-of-scope={m.get(\"false_positives_out_of_scope\",0)})')
print(f'  False Negatives: {m[\"false_negatives\"]}')
print(f'  Precision:       {m[\"precision\"]:.3f} (in-scope: {m.get(\"precision_in_scope\",0):.3f})')
print(f'  Recall:          {m[\"recall\"]:.3f}')
print(f'  F1:              {m[\"f1_score\"]:.3f}')
risk = m.get('recall_by_risk', {})
for k in sorted(risk.keys()):
    print(f'  Recall Risk {k}:   {risk[k]:.3f}')
print(f'  Total Found:     {m[\"total_found\"]}')
print(f'  Total Gold:      {m[\"total_gold\"]}')
"
else
    echo "  Metrics file not found: $METRICS_FILE"
fi

echo ""
echo "=== Done. Results in: eval/$RUN_ID/ ==="
