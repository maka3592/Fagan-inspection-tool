# Requirements Checklist

This document tracks all professor requirements for the Fagan Inspection Tool replication study.

**Last Updated:** 2026-02-01
**Verification Script:** `fagan verify` or `python scripts/verify_requirements.py`

---

## Summary Table

| ID | Requirement | Status | Evidence |
|----|-------------|--------|----------|
| RA | fagan --help runs successfully | PASS | CLI command works |
| RB | fagan dry-run works without API keys | PASS | dry-run completes |
| RC | fagan run requires API key | SKIP | Test requires OPENAI_API_KEY |
| R1 | Run-ID suffix logic prevents overwriting | PASS | `process.py` |
| R2 | config_snapshot.json saved per run | PASS | `runs/<id>/config_snapshot.json` |
| R3 | metadata.json contains prompt_versions/llm_params | PASS | `schemas.py` |
| R4 | C1 config has 3 UBR reviewers | PASS | `configs/examples/c1_ubr.yaml` |
| R5 | reviewer_outputs.json has 3 entries (C1) | SKIP | Requires actual run |
| R6 | UBR prompt prioritizes Design/MSC | PASS | `prompts/reviewer_ubr.txt` |
| R7 | GoldLoader reads .xls (xlrd dependency) | PASS | `pyproject.toml` |
| R8 | Gold standard contains 36 defects | PASS | GoldLoader verified |
| R9 | Gold file protected (LeakageGuard) | PASS | `leakage_guard.py` |
| R10 | fagan eval outputs: metrics/matches/CSV | PASS | `cli.py` |
| R11 | FP = TotalFound - TP - Duplicates | PASS | `metrics.py` |
| R12 | FP split in-scope/out-of-scope | PASS | `metrics.py` |
| R13 | --match-threshold parameter + stored | PASS | `cli.py` + `schemas.py` |
| R14 | Manual validation: export matches_manual.csv | PASS | `manual-template` command |
| R15 | Manual validation: metrics_manual.json | PASS | `manual-eval` command |
| R16 | fagan report with FP split + threshold | PASS | `cli.py` |
| R17 | Verify never writes to artifacts/gold/ | PASS | LeakageGuard protects gold |
| R18 | Signal-gated matching prevents false partials | PASS | `matcher.py` Gate 2 + `test_matching_validity.py` |
| R19 | Multi-position conservative filter | PASS | `matcher.py` Gate A3 + tests |
| R20 | Normalized desc similarity + feature flags | PASS | `position_tokens.py` + `matcher.py` A2 |
| R21 | Matching validity documented | PASS | `docs/MATCHING_VALIDITY.md` |
| R22 | CBR prompt enforces strict JSON + signal names | PASS | `prompts/reviewer_cbr.txt` v2.0 |
| R23 | Domain-specific CBR checklist (7 items) | PASS | `configs/checklists/cbr_minimal.yaml` v2.0 |
| R24 | c1_cbr.yaml: 3 CBR reviewers with scope partitioning | PASS | `configs/examples/c1_cbr.yaml` |
| R25 | CBR routes to correct prompt + loads checklist | PASS | `process.py` + `reviewer_agent.py` |
| R26 | CBR dry-run produces 3 reviewer outputs | PASS | `test_process.py::TestCbrDryRun` |
| R27 | CBR checklist loaded as artifact (Phase 1 visible) | PASS | `artifacts/input/checklists/cbr_checklist_v2.yaml` |
| R28 | UBR guide not in CBR config | PASS | `test_process.py::TestC1CbrConfig` |

---

## Detailed Requirements

### Runnable Checks (RA-RC)

#### RA: fagan --help
**Description:** CLI help command works.

**Status:** PASS

**Verification:**
```bash
fagan --help
```

---

#### RB: fagan dry-run (no API)
**Description:** `fagan dry-run` must work without API keys, generating deterministic output.

**Status:** PASS

**Evidence:**
- Command: `fagan dry-run`
- Output: `runs/demo_dry_run/` with deterministic defects

**Verification:**
```bash
unset OPENAI_API_KEY
fagan dry-run
ls runs/demo_dry_run/
```

---

#### RC: fagan run (with API)
**Description:** `fagan run --config <config.yaml>` must work with OPENAI_API_KEY set.

**Status:** SKIP (if API key not available)

**Evidence:**
- File: `src/fagan_tool/cli.py`
- Requires: OPENAI_API_KEY environment variable

**Verification:**
```bash
export OPENAI_API_KEY="..."
fagan run --config configs/examples/c1_ubr.yaml
```

---

### Feature Requirements (R1-R17)

#### R1: Run-ID Uniqueness
**Description:** If a run directory exists, the system must auto-increment the run ID (_002, _003, etc.).

**Status:** PASS

**Evidence:**
- File: `src/fagan_tool/core/process.py`
- Method: `FaganProcess._ensure_unique_run_id()`

---

#### R2: config_snapshot.json
**Description:** Each run must save the exact configuration used.

**Status:** PASS

**Evidence:**
- Output: `runs/<run_id>/config_snapshot.json`

---

#### R3: Metadata Fields
**Description:** Prompt versions, LLM params, and artifacts must be recorded in metadata.

**Status:** PASS

**Evidence:**
- File: `src/fagan_tool/core/schemas.py`
- Fields: `prompt_versions`, `llm_params`, `artifacts`

---

#### R4: C1 Three Reviewers
**Description:** Condition C1 configuration must specify 3 independent UBR reviewers.

**Status:** PASS

**Evidence:**
- File: `configs/examples/c1_ubr.yaml`
- Config: `reading_techniques: ["UBR", "UBR", "UBR"]`

---

#### R5: Reviewer Outputs
**Description:** For C1 runs, the reviewer output must contain 3 separate entries.

**Status:** SKIP (requires actual run)

**Verification:**
```bash
cat runs/c1_ubr_run_001/reviewer_outputs.json | jq 'length'
```

---

#### R6: UBR Prompt Priority
**Description:** UBR prompt must prioritize Design/MSC sections (3.x, 4.x) over Use Cases.

**Status:** PASS

**Evidence:**
- File: `prompts/reviewer_ubr.txt`
- Contains: "DESIGN/MSC PRIORITY", "AVOID USE CASE-ONLY"

---

#### R7: XLS Support
**Description:** GoldLoader must read .xls (old Excel) files with xlrd.

**Status:** PASS

**Evidence:**
- File: `pyproject.toml` contains `xlrd>=2.0.1`

---

#### R8: Gold Defect Count
**Description:** Gold standard file must contain exactly 36 defects.

**Status:** PASS

**Evidence:**
- File: `artifacts/gold/Faults_List_In_ver6.xls`
- Count: 36 defects (verified via GoldLoader)

---

#### R9: Gold Integrity
**Description:** Gold file is never modified by the tool.

**Status:** PASS

**Evidence:**
- File: `src/fagan_tool/utils/leakage_guard.py`
- LeakageGuard prevents write access to gold paths

---

#### R10: Evaluation Outputs
**Description:** `fagan eval` must generate metrics.json, matches.json, and matches_enriched.csv.

**Status:** PASS

**Evidence:**
- File: `src/fagan_tool/cli.py`
- Outputs: `eval/<run_id>/metrics.json`, `matches.json`, `matches_enriched.csv`

---

#### R11: FP Formula
**Description:** FP = TotalFound - TP - Duplicates

**Status:** PASS

**Evidence:**
- File: `src/fagan_tool/evaluation/metrics.py`
- Code: `false_positives = total_found - true_positives - duplicates`

---

#### R12: FP Split
**Description:** False positives split into in-scope and out-of-scope.

**Status:** PASS

**Evidence:**
- File: `src/fagan_tool/evaluation/metrics.py`
- Fields: `false_positives_in_scope`, `false_positives_out_of_scope`

---

#### R13: Match Threshold
**Description:** `--match-threshold` parameter configurable and stored in metrics.

**Status:** PASS

**Evidence:**
- CLI: `--match-threshold` option in eval command
- Stored in: `evaluation_metadata.matcher_thresholds`

---

#### R14: Manual Template
**Description:** Export matches_manual.csv for human validation.

**Status:** PASS

**Evidence:**
- Script: `scripts/create_manual_template.py`
- CLI: `fagan manual-template --run <run_id>`

---

#### R15: Manual Metrics
**Description:** Calculate metrics from manual validation.

**Status:** PASS

**Evidence:**
- Script: `scripts/calculate_manual_metrics.py`
- CLI: `fagan manual-eval --run <run_id>`
- Output: `eval/<run_id>/metrics_manual.json`

---

#### R16: Report Generation
**Description:** `fagan report` generates comprehensive markdown report.

**Status:** PASS

**Evidence:**
- File: `src/fagan_tool/cli.py`
- Output: `eval/<run_id>/report.md`
- Includes: FP split, threshold, metrics

---

#### R17: No Gold Writes
**Description:** Verification and run scripts never write to artifacts/gold/.

**Status:** PASS

**Evidence:**
- LeakageGuard protects gold directory
- No write patterns found in core modules

---

### CBR Integration Requirements (R22-R26)

#### R22: CBR Prompt Quality
**Description:** CBR reviewer prompt enforces strict JSON output, signal-first descriptions, canonical positions, and max 4-6 defects per reviewer.

**Status:** PASS

**Evidence:**
- File: `prompts/reviewer_cbr.txt` (v2.0, 129 lines)
- Contains: JSON output format, position rules, description style, CBR methodology
- Matches UBR prompt quality standards

---

#### R23: Domain-Specific Checklist
**Description:** CBR checklist contains 7 domain-specific categories targeting the taxi dispatch system.

**Status:** PASS

**Evidence:**
- File: `configs/checklists/cbr_minimal.yaml` (v2.0)
- Categories: CL1 Missing Signals, CL2 Interface Inconsistencies, CL3 Parameter Type Mismatches, CL4 Acknowledgment Completeness, CL5 Timeout Specifications, CL6 Table 1 vs MSC Consistency, CL7 Traceability Gaps

---

#### R24: C1 CBR Three Reviewers
**Description:** CBR config with 3 independent reviewers using scope partitioning.

**Status:** PASS

**Evidence:**
- File: `configs/examples/c1_cbr.yaml`
- Config: `reading_techniques: ["CBR", "CBR", "CBR"]`
- Scope: Reviewer 1 (Table 1, 3.1-3.2.2), Reviewer 2 (3.3-3.4.2), Reviewer 3 (4.1-4.2)

---

#### R25: CBR Pipeline Routing
**Description:** CBR technique routes to `reviewer_cbr.txt` and loads checklist from `extra_config.checklist_path`.

**Status:** PASS

**Evidence:**
- File: `src/fagan_tool/agents/reviewer_agent.py` maps `CBR` → `reviewer_cbr.txt`
- File: `src/fagan_tool/core/process.py` reads `checklist_path` from `extra_config`

---

#### R26: CBR Dry-Run
**Description:** `fagan dry-run` with CBR config produces 3 reviewer outputs.

**Status:** PASS

**Evidence:**
- Test: `tests/test_process.py::TestCbrDryRun`
- Verified: 3 CBR reviewer outputs, correct reviewer IDs, defects generated

---

#### R27: CBR Checklist as Artifact
**Description:** CBR checklist is loaded as a Phase 1 artifact, visible in run log and reviewer context.

**Status:** PASS

**Evidence:**
- File: `artifacts/input/checklists/cbr_checklist_v2.yaml` (copy of `configs/checklists/cbr_minimal.yaml`)
- Config: `c1_cbr.yaml` lists `checklists/cbr_checklist_v2.yaml` in `artifacts:`
- Type: `artifact_loader._infer_type()` returns `"checklist"` for this path
- Test: `tests/test_process.py::TestCbrChecklistArtifact`

---

#### R28: No UBR Guide in CBR Config
**Description:** CBR configs do not reference the UBR-specific guide PDF.

**Status:** PASS

**Evidence:**
- `configs/examples/c1_cbr.yaml` — no `GuideUBR_rankbased_v2.pdf`
- `configs/examples/c2_cbr.yaml` — no `GuideUBR_rankbased_v2.pdf`
- Test: `tests/test_process.py::TestC1CbrConfig::test_ubr_guide_not_in_cbr_artifacts`

---

## Verification

Run automated verification:

```bash
# Using CLI command
fagan verify

# Using standalone script
python scripts/verify_requirements.py

# JSON output
python scripts/verify_requirements.py --json

# Save to file
python scripts/verify_requirements.py --output results.json
```

Exit codes:
- 0: No FAILs (PASS, PARTIAL, SKIP all acceptable)
- 1: At least one FAIL

---

## Manual Validation Workflow

For thesis-grade precision, manually validate automated matches:

### Step 1: Create Manual Template
```bash
fagan manual-template --run c1_ubr_run_001
```

### Step 2: Review and Annotate
1. Open `eval/c1_ubr_run_001/matches_manual.csv`
2. Set `manual_is_true_match` to `TRUE` for correct matches
3. Add notes in `manual_notes` column
4. Save

### Step 3: Calculate Manual Metrics
```bash
fagan manual-eval --run c1_ubr_run_001
```

This creates `eval/c1_ubr_run_001/metrics_manual.json` with human-validated precision/recall.

---

## Change Log

| Date | Change | Author |
|------|--------|--------|
| 2026-01-25 | Initial requirements analysis | Claude |
| 2026-01-25 | Fixed R7: Added xlrd dependency | Claude |
| 2026-01-25 | Fixed R14: Implemented manual-template | Claude |
| 2026-01-25 | Fixed R15: Implemented manual-eval | Claude |
| 2026-01-25 | Added fagan verify command | Claude |
| 2026-01-25 | Moved to docs/REQUIREMENTS_CHECKLIST.md | Claude |
| 2026-01-25 | Fixed R17 check (false positive) | Claude |
| 2026-02-01 | Added R18-R21: Matching validity improvements | Claude |
| 2026-02-01 | Added R22-R26: CBR integration (prompt, checklist, config, tests) | Claude |
| 2026-02-01 | Added R27-R28: CBR checklist as artifact, UBR guide removed from CBR | Claude |
