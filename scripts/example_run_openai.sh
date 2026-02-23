#!/usr/bin/env bash
# Example script for running Fagan inspection with OpenAI GPT-5-mini
#
# This script:
# - Loads .env safely (compatible with bash, no zsh interactive comment issues)
# - Generates a unique RUN_ID
# - Runs fagan inspection
# - Evaluates against gold standard
# - Prints directory listings
#
# Usage: bash scripts/example_run_openai.sh

set -euo pipefail

echo "=== Fagan OpenAI Example Run ==="
echo ""

# Load .env if it exists (bash-safe method)
if [[ -f .env ]]; then
    echo "Loading .env file..."
    set -a
    source .env
    set +a
fi

# Check OPENAI_API_KEY
if [[ -z "${OPENAI_API_KEY:-}" ]]; then
    echo "ERROR: OPENAI_API_KEY is not set"
    echo "Please set it in .env or export it before running this script"
    exit 1
fi

# Show API key prefix (first 8 chars) for verification
KEY_PREFIX="${OPENAI_API_KEY:0:8}"
echo "OPENAI_API_KEY is set (prefix: ${KEY_PREFIX}...)"
echo ""

# Generate unique RUN_ID with timestamp
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
RUN_ID="openai_gpt5_${TIMESTAMP}"
echo "Generated RUN_ID: ${RUN_ID}"
echo ""

# Configuration file to use
CONFIG_FILE="configs/examples/c1_ubr.yaml"

# Check config exists
if [[ ! -f "${CONFIG_FILE}" ]]; then
    echo "ERROR: Config file not found: ${CONFIG_FILE}"
    exit 1
fi

echo "Using config: ${CONFIG_FILE}"
echo ""

# Run the inspection
echo "=== Running Fagan Inspection ==="
echo "Command: fagan run --config ${CONFIG_FILE} --run-id ${RUN_ID}"
echo ""

if ! fagan run --config "${CONFIG_FILE}" --run-id "${RUN_ID}"; then
    echo ""
    echo "ERROR: fagan run failed"
    echo "Check the output above for details"
    exit 1
fi

echo ""
echo "=== Inspection Complete ==="
echo ""

# Verify output exists
OUTPUT_FILE="runs/${RUN_ID}/final_defects.json"
if [[ -f "${OUTPUT_FILE}" ]]; then
    echo "SUCCESS: Output file exists: ${OUTPUT_FILE}"
    DEFECT_COUNT=$(python3 -c "import json; print(len(json.load(open('${OUTPUT_FILE}'))))" 2>/dev/null || echo "?")
    echo "Defects found: ${DEFECT_COUNT}"
else
    echo "WARNING: Output file not found: ${OUTPUT_FILE}"
fi
echo ""

# Gold standard file (never modified, read-only)
GOLD_FILE="artifacts/gold/Faults_List_In_ver6.xls"

# Check gold file exists
if [[ ! -f "${GOLD_FILE}" ]]; then
    echo "ERROR: Gold standard file not found: ${GOLD_FILE}"
    exit 1
fi

echo "=== Running Evaluation ==="
echo "Command: fagan eval --run ${RUN_ID} --gold ${GOLD_FILE} --match-threshold 0.65"
echo ""

if ! fagan eval --run "${RUN_ID}" --gold "${GOLD_FILE}" --match-threshold 0.65; then
    echo ""
    echo "ERROR: fagan eval failed"
    exit 1
fi

echo ""
echo "=== Evaluation Complete ==="
echo ""

# Print directory listings
echo "=== Directory Listings ==="
echo ""
echo "runs/${RUN_ID}/:"
ls -la "runs/${RUN_ID}/" 2>/dev/null || echo "  (directory not found)"
echo ""
echo "eval/${RUN_ID}/:"
ls -la "eval/${RUN_ID}/" 2>/dev/null || echo "  (directory not found)"
echo ""

echo "=== Done ==="
echo "Run ID: ${RUN_ID}"
echo ""
echo "Next steps:"
echo "  - View defects: cat runs/${RUN_ID}/final_defects.json | jq '.[:3]'"
echo "  - View metrics: cat eval/${RUN_ID}/metrics.json | jq '.'"
echo "  - Generate report: fagan report --run ${RUN_ID}"
