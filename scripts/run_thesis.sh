#!/bin/bash
# Thesis Run Script - uses gpt-4o-mini (stable, recommended)
# Usage: ./scripts/run_thesis.sh [optional_run_id_suffix]

set -e

# Load environment (API keys)
if [ -f .env ]; then
    set -a
    source .env
    set +a
    echo "✓ Loaded .env"
else
    echo "⚠ No .env file found - ensure OPENAI_API_KEY is set"
fi

# Check API key
if [ -z "$OPENAI_API_KEY" ]; then
    echo "✗ OPENAI_API_KEY not set"
    exit 1
fi

# Generate run ID with timestamp
SUFFIX="${1:-}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
if [ -n "$SUFFIX" ]; then
    RUN_ID="thesis_4omini_${SUFFIX}_${TIMESTAMP}"
else
    RUN_ID="thesis_4omini_${TIMESTAMP}"
fi

echo ""
echo "=== Thesis Run: ${RUN_ID} ==="
echo "Model: gpt-4o-mini"
echo ""

# Run inspection
echo ">>> Running inspection..."
fagan run --config configs/examples/c1_ubr.yaml --run-id "$RUN_ID"

# Check for incomplete reviewers
echo ""
echo ">>> Checking for incomplete outputs..."
INCOMPLETE=$(python -c "
import json
with open('runs/${RUN_ID}/meeting_output.json') as f:
    data = json.load(f)
    inc_rev = data.get('incomplete_reviewers', [])
    parse_err = data.get('json_parse_errors', [])
    if inc_rev:
        print(f'⚠ Incomplete reviewers: {len(inc_rev)}')
    if parse_err:
        print(f'⚠ JSON parse errors: {len(parse_err)}')
    if not inc_rev and not parse_err:
        print('✓ All reviewers complete, no parse errors')
")
echo "$INCOMPLETE"

# Run evaluation
echo ""
echo ">>> Running evaluation..."
fagan eval --run "$RUN_ID" --gold artifacts/gold/Faults_List_In_ver6.xls --match-threshold 0.65

# Show metrics
echo ""
echo ">>> Metrics Summary:"
python -c "
import json
with open('eval/${RUN_ID}/metrics.json') as f:
    m = json.load(f)
    print(f'  Precision:  {m[\"precision\"]:.3f}')
    print(f'  Recall:     {m[\"recall\"]:.3f}')
    print(f'  F1 Score:   {m[\"f1_score\"]:.3f}')
    print(f'  TP (exact): {m.get(\"tp_exact\", \"N/A\")}')
    print(f'  TP (partial): {m.get(\"tp_partial\", \"N/A\")}')
"

echo ""
echo "=== Run Complete ==="
echo "Results: runs/${RUN_ID}/"
echo "Eval:    eval/${RUN_ID}/"
