# UBR Pipeline Implementation - Point 2

**Date:** 2026-02-22
**Requirement:** Masterarbeit Punkt 2 – UBR methodisch korrekt in Pipeline ausführen

---

## Summary

This document traces the changes made to ensure UBR (Usage-Based Reading) is executed **methodically correct** in the pipeline, following Petersen ESEM'08 methodology rather than just being a prompt instruction.

---

## Changed Files

| File | Status | Reason |
|------|--------|--------|
| `src/fagan_tool/core/schemas.py` | **Updated** | Added UBR-specific metadata fields to RunMetadata |
| `src/fagan_tool/core/process.py` | **Updated** | Added `_build_ubr_context()` method for structured UBR execution |
| `configs/examples/c1_ubr.yaml` | **Updated** | Added RB-UBR/TC-UBR config flags and use case metadata |

---

## Implementation Details

### 1. UBR Variants (RB-UBR vs TC-UBR)

**Configuration Flag:** `extra_config.ubr_variant`

| Variant | Description | Use When |
|---------|-------------|----------|
| **RB-UBR** (Rank-Based) | Process use cases in priority order, no skipping | Default, use all available time |
| **TC-UBR** (Time-Controlled) | Respect time budgets per use case | Time-constrained inspections |

**Example config:**
```yaml
extra_config:
  ubr_variant: "RB-UBR"  # or "TC-UBR"
```

### 2. Use Case Artifact Reference

**Configuration Field:** `extra_config.use_case_artifact`

Specifies which artifact contains the prioritized use cases for UBR tracing:

```yaml
extra_config:
  use_case_artifact: "usecases/UseCasesRank_v3.4.pdf"
  use_case_count: 19
```

### 3. Time Budgets (TC-UBR only)

For time-controlled UBR, per-use-case time budgets can be specified:

```yaml
extra_config:
  ubr_variant: "TC-UBR"
  time_budgets:
    "UC1.1": 8
    "UC1.2": 6
    "UC2.1": 10
```

### 4. Run Metadata Tracking

New fields in `RunMetadata` (schemas.py:274-289):

| Field | Type | Description |
|-------|------|-------------|
| `ubr_variant` | `Optional[str]` | "RB-UBR" or "TC-UBR" |
| `ubr_use_case_source` | `Optional[str]` | Path to use case artifact |
| `ubr_use_case_count` | `Optional[int]` | Number of use cases |
| `ubr_time_budgets` | `Optional[Dict[str, int]]` | TC-UBR time allocations |

These fields are automatically populated in `metadata.json` for every UBR run.

### 5. Context Injection (`_build_ubr_context()`)

The `_build_ubr_context()` method in process.py:375-429 generates structured context for UBR reviewers:

```
## UBR Inspection Mode: RB-UBR

### RB-UBR Mode (Rank-Based)
Process use cases in the order they appear (priority order).
Do not skip use cases; work through all of them systematically.

### Use Case Source: usecases/UseCasesRank_v3.4.pdf

### UBR Inspection Process
1. Start with the first (highest-priority) use case.
2. Trace through the design document following the Tasks of the use case.
3. Check if the design provides complete and correct information for the use case goal.
4. Record defects where the design fails to support the use case.
5. Proceed to the next use case and repeat.

Use the Purpose, Tasks, and Variants of each use case as your analysis basis.
```

---

## Literature Source

**Petersen et al., ESEM 2008** - Usage-Based Reading methodology

Key principles implemented:
1. **Use-case-driven inspection**: Use cases as primary analysis units
2. **Priority ordering**: RB-UBR processes in rank order
3. **Task-based tracing**: Follow use case Tasks through design
4. **Goal verification**: Check design supports use case goals
5. **Systematic coverage**: No skipping (RB-UBR) or time-aware (TC-UBR)

---

## Definition of Done (Completed)

- [x] Config flag `ubr_variant` distinguishes RB-UBR vs TC-UBR
- [x] Use case artifact path stored in config and metadata
- [x] Purpose/Tasks/Variants used as analysis basis (context injection)
- [x] Time budgets supported for TC-UBR
- [x] Run metadata tracks UBR execution parameters
- [x] Gold standard unchanged (checksum verified)

---

## Example Run

```bash
# RB-UBR (default)
fagan run --config configs/examples/c1_ubr.yaml

# Check metadata
jq '.ubr_variant, .ubr_use_case_source' runs/c1_ubr_run_001/metadata.json
# "RB-UBR"
# "usecases/UseCasesRank_v3.4.pdf"
```

---

## Verification

- Gold standard: **UNCHANGED** (SHA256: `936df6d9...`)
- JSON output schema: **UNCHANGED**
- Python `.format()` compatibility: **PRESERVED**
- All existing tests: **PASS**

---

## Hardening (Post-Point 2)

### Configuration Validation

The pipeline performs fail-fast validation when UBR techniques are used:

| Check | Error Message |
|-------|---------------|
| Invalid `ubr_variant` | `Invalid ubr_variant 'X'. Must be one of: RB-UBR, TC-UBR` |
| Missing `use_case_artifact` | `UBR use_case_artifact not found: <path>` |

**Code location:** `process.py:_validate_ubr_config()`

### TC-UBR Budget Detection

When `ubr_variant = "TC-UBR"` but no `time_budgets` are provided:

1. **Console warning**: `⚠ TC-UBR mode without explicit time_budgets in config...`
2. **Metadata flag**: `ubr_tc_budgets_detected: false`

This ensures transparency without silent fallback to RB-UBR behavior.

### New Tests (TestUBRConfigValidation)

| Test | Purpose |
|------|---------|
| `test_invalid_ubr_variant_raises_error` | Invalid variant → clear ValueError |
| `test_valid_rb_ubr_variant_passes` | RB-UBR accepted |
| `test_valid_tc_ubr_variant_passes` | TC-UBR accepted |
| `test_missing_use_case_artifact_raises_error` | Missing artifact → ValueError |
| `test_ubr_context_contains_methodology_structure` | Purpose/Tasks/Variants in context |

---

## Commit Message Template

```
feat(process): implement UBR methodology in pipeline (Point 2)

- Add RB-UBR/TC-UBR variant config flag
- Add _build_ubr_context() for structured use-case-driven context
- Track UBR execution metadata (variant, use case source, time budgets)
- Update c1_ubr.yaml with UBR-specific configuration

Per Petersen ESEM'08: use cases as primary analysis units,
Purpose/Tasks/Variants as inspection basis.

Gold standard: UNCHANGED
```
