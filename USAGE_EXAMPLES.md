# Usage Examples

## Complete Workflow Example

### Step 1: Setup

```bash
# Install dependencies
pip install -r requirements.txt

# Set API key
export OPENAI_API_KEY="your-api-key-here"
```

### Step 2: Test with Dry Run

```bash
# Run without API calls to verify setup
fagan dry-run
```

Expected output:
```
Running dry-run inspection...
Note: This mode generates simulated outputs without API calls

Phase 1: Planning
  Entry check: Pass (dry run)

Phase 2: Kick-Off
  Roles assigned and rules clarified

Phase 3: Preparation
  Reading technique guides distributed

Phase 4: Individual Inspection
  1 reviewers completed inspection
    reviewer_1_ubr (UBR): 3 defects found

Phase 5: Inspection Meeting
  Consolidated: 5 defects
  Duplicates removed: 4
  Exit decision: Conditional Accept (dry run)

Phase 6: Rework
  Change requests generated

Phase 7: Follow-Up
  Logs complete: Yes
  Evidence quality: Good

✓ Inspection completed successfully!
Run ID: demo_dry_run
Generated 5 simulated defects
Results: runs/demo_dry_run/
```

### Step 3: Place Your Artifacts

```bash
# Place your design documents
cp your_design.pdf artifacts/input/design/

# Place use cases
cp your_usecases.pdf artifacts/input/usecases/

# Place requirements (optional)
cp your_requirements.pdf artifacts/input/requirements/
```

### Step 4: Run Real Inspection (C1: UBR)

```bash
fagan run --config configs/examples/c1_ubr.yaml
```

This will:
1. Load design document and use cases
2. Run UBR-based inspection
3. Generate defect findings
4. Save results to `runs/c1_ubr_run_001/`

### Step 5: Evaluate Against Gold Standard

```bash
# Place your gold standard file
cp Faults_List_In_ver6.xls artifacts/gold/

# Run evaluation
fagan eval --run c1_ubr_run_001 --gold artifacts/gold/Faults_List_In_ver6.xls
```

Expected output:
```
Evaluating run: c1_ubr_run_001
Loading gold standard from artifacts/gold/Faults_List_In_ver6.xls
  Gold defects: 30
Matching defects...
Calculating metrics...

Evaluation Metrics:

┏━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━┓
┃ Metric             ┃  Value ┃
┡━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━┩
│ Total Found        │     25 │
│ Total Gold         │     30 │
│ True Positives     │     20 │
│ False Positives    │      5 │
│ False Negatives    │     10 │
│ Duplicates         │      0 │
│                    │        │
│ Precision          │  0.800 │
│ Recall             │  0.667 │
│ F1 Score           │  0.727 │
└────────────────────┴────────┘

Recall by Risk Level:

┏━━━━━━━━━━━━┳━━━━━━━━┓
┃ Risk Level ┃ Recall ┃
┡━━━━━━━━━━━━╇━━━━━━━━┩
│ A          │  0.750 │
│ B          │  0.650 │
│ C          │  0.600 │
│ UNK        │  0.000 │
└────────────┴────────┘

Results saved to eval/c1_ubr_run_001/
```

### Step 6: Generate Report

```bash
fagan report --run c1_ubr_run_001
```

This creates `eval/c1_ubr_run_001/report.md` with:
- Summary statistics
- Performance metrics
- Risk-level breakdown
- Interpretation guidelines

## Running Different Conditions

### C2: Checklist-Based Reading

```bash
fagan run --config configs/examples/c2_cbr.yaml
fagan eval --run c2_cbr_run_001 --gold artifacts/gold/Faults_List_In_ver6.xls
fagan report --run c2_cbr_run_001
```

### C3: PBR Team (3 Reviewers)

```bash
fagan run --config configs/examples/c3_pbr_team.yaml
fagan eval --run c3_pbr_team_run_001 --gold artifacts/gold/Faults_List_In_ver6.xls
fagan report --run c3_pbr_team_run_001
```

### C4: Hybrid (All Techniques)

```bash
fagan run --config configs/examples/c4_hybrid.yaml
fagan eval --run c4_hybrid_run_001 --gold artifacts/gold/Faults_List_In_ver6.xls
fagan report --run c4_hybrid_run_001
```

## Custom Configuration

Create your own config file:

```yaml
# my_inspection.yaml
inspection_id: "my_custom_run_001"
condition: "C1_UBR"

reading_techniques:
  - "UBR"

artifacts:
  - "design/my_design.pdf"
  - "usecases/my_usecases.pdf"

llm_params:
  provider: "openai"
  model: "gpt-4o-mini"
  temperature: 0.2
  max_tokens: 4096

dry_run: false
```

Run it:

```bash
fagan run --config my_inspection.yaml
```

## Multiple Runs for Statistical Analysis

```bash
# Run same config 5 times for statistical analysis
for i in {1..5}; do
  # Update inspection_id in config or use sed
  sed "s/run_001/run_00$i/" configs/examples/c1_ubr.yaml > temp_config.yaml
  fagan run --config temp_config.yaml
done

# Evaluate all runs
for i in {1..5}; do
  fagan eval --run c1_ubr_run_00$i --gold artifacts/gold/Faults_List_In_ver6.xls
done

# Compare metrics across runs
cat eval/c1_ubr_run_00*/metrics.json | jq '.recall'
```

## Inspecting Results

### View Found Defects

```bash
cat runs/c1_ubr_run_001/final_defects.json | jq '.[0]'
```

Example output:
```json
{
  "id": "reviewer_1_ubr_abc123",
  "position": "Section 3.2",
  "page_hint": "p. 15",
  "risk": "A",
  "fault_type": "M",
  "description": "Missing error handling for null pointer exception",
  "evidence": "Section 3.2 does not specify error handling (p. 15)",
  "confidence": 0.9,
  "flags": [],
  "reviewer_id": "reviewer_1_ubr",
  "technique": "UBR"
}
```

### View Match Details

```bash
cat eval/c1_ubr_run_001/matches.json | jq '.[] | select(.match_type == "EXACT")'
```

### View Meeting Minutes

```bash
cat runs/c1_ubr_run_001/meeting_output.json | jq '.minutes'
```

## Troubleshooting Common Issues

### Issue: Rate Limiting

If you hit API rate limits:

```yaml
# Add delays in config (not yet implemented, but you can batch)
# Or use OpenAI instead:
llm_params:
  provider: "openai"
  model: "gpt-4-turbo-preview"
  temperature: 0.2
  max_tokens: 4096
```

### Issue: Large PDFs

For very large PDFs (>100 pages), consider:

1. Splitting the document
2. Increasing max_tokens
3. Using chunking strategy (implemented in PDFExtractor)

### Issue: Poor Matching Results

If matching quality is low:

1. Check position formatting in gold standard
2. Adjust matcher thresholds using `--match-threshold`
3. Review normalization rules in `matcher.py`

## Threshold Sensitivity Analysis

The `--match-threshold` parameter controls how strict the matching is:

```bash
# Default threshold (0.60) - balanced matching
fagan eval --run my_run

# Lower threshold (0.50) - more lenient, higher recall
fagan eval --run my_run --match-threshold 0.50

# Higher threshold (0.70) - stricter, higher precision
fagan eval --run my_run --match-threshold 0.70
```

**How threshold affects results:**
- **Lower threshold**: More defects match as partial (higher TP, lower FP, higher Recall)
- **Higher threshold**: Fewer matches (lower TP, higher FP, lower Recall, potentially higher Precision)

For thesis-grade reproducible evaluation, always document the threshold used:

```bash
# Run with explicit threshold for reproducibility
fagan eval --run experiment_001 --match-threshold 0.65 --gold artifacts/gold/Faults_List.xls

# The threshold is stored in metrics.json under evaluation_metadata.matcher_thresholds
```

**TP Breakdown (Exact vs Partial):**
- **Exact matches** (similarity >= 0.85): High-confidence matches
- **Partial matches** (threshold <= similarity < 0.85): Related defects

The metrics output now includes:
- `true_positives_exact`: Count of exact matches
- `true_positives_partial`: Count of partial matches
- `similarity_score_mean_tp`: Mean similarity of all TPs
- `similarity_score_min_tp` / `similarity_score_max_tp`: Range of TP similarities

## Best Practices

1. **Always run dry-run first** to verify setup
2. **Use version control** for configs and prompts
3. **Document prompt changes** in prompt_versions
4. **Run multiple iterations** for statistical significance
5. **Keep gold standard separate** - never mix with input artifacts
6. **Review meeting minutes** to understand consolidation decisions
7. **Compare conditions** to evaluate technique effectiveness

## Advanced Usage

### Programmatic Access

```python
from pathlib import Path
from fagan_tool.core.process import FaganProcess
from fagan_tool.core.schemas import InspectionConfig, ConditionType, ReadingTechnique, LLMParams

# Create config programmatically
config = InspectionConfig(
    inspection_id="prog_run_001",
    condition=ConditionType.C1_UBR,
    reading_techniques=[ReadingTechnique.UBR],
    artifacts=["design/doc.pdf"],
    llm_params=LLMParams(
        provider="openai",
        model="gpt-4o-mini",
        temperature=0.2,
        max_tokens=4096,
    ),
    dry_run=False,
)

# Run inspection
process = FaganProcess(config)
run = process.run()

# Access results
print(f"Found {len(run.final_defects)} defects")
for defect in run.final_defects:
    print(f"- {defect.position}: {defect.description}")
```

### Custom Checklist

Edit `configs/checklists/cbr_minimal.yaml` or create your own:

```yaml
# my_checklist.yaml
checklist_version: "1.0"
description: "My custom checklist"

categories:
  - name: "Security"
    items:
      - "Are authentication mechanisms specified?"
      - "Is sensitive data encrypted?"
      - "Are access controls defined?"
```

Reference it in your config:

```yaml
extra_config:
  checklist_path: "configs/checklists/my_checklist.yaml"
```

## Requirements Verification

Verify all professor requirements are met:

```bash
# Run automated verification
fagan verify

# Or use the standalone script
python scripts/verify_requirements.py
```

Expected output:
```
Requirements Verification Report
┏━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ ID      ┃ Description                 ┃ Status ┃ Evidence                    ┃
┡━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┩
│ R1      │ Tool runs end-to-end...     │  PASS  │ dry-run command defined...  │
...
Summary:
  PASS: 19
  PARTIAL: 0
  FAIL: 0
```

See `REQUIREMENTS_CHECKLIST.md` for detailed requirements.

## Manual Validation Workflow

For thesis-grade precision, you can manually validate automated matches:

### Step 1: Create Manual Template

```bash
# After running eval, create a manual validation template
fagan manual-template --run c1_ubr_run_001
```

This creates `eval/c1_ubr_run_001/matches_manual.csv` with:
- All columns from `matches_enriched.csv`
- `manual_is_true_match` column (default: FALSE)
- `manual_notes` column for annotations

### Step 2: Manual Review

1. Open `matches_manual.csv` in a spreadsheet editor
2. Review each match row
3. Set `manual_is_true_match` to `TRUE` if the match is correct
4. Add notes in `manual_notes` column if needed
5. Save the file

### Step 3: Calculate Manual Metrics

```bash
fagan manual-eval --run c1_ubr_run_001
```

Expected output:
```
Manual Validation Metrics: c1_ubr_run_001

┏━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━┓
┃ Metric                  ┃  Value ┃
┡━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━┩
│ Total Matches Reviewed  │     25 │
│ Manual True Positives   │     18 │
│ Manual False Positives  │      7 │
│ Total Gold              │     36 │
│ False Negatives         │     18 │
│ Precision               │  0.720 │
│ Recall                  │  0.500 │
│ F1 Score                │  0.590 │
└─────────────────────────┴────────┘

Metrics saved to: eval/c1_ubr_run_001/metrics_manual.json
```

### Comparison

You now have two sets of metrics:
- `metrics.json` - Automated matching (algorithmic)
- `metrics_manual.json` - Human-validated matching (ground truth)

This allows for:
- Calibrating automated matcher thresholds
- Reporting human-validated precision/recall for thesis
- Identifying edge cases where automated matching fails
