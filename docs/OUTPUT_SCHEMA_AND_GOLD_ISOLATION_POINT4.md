# Output Schema Standardization and Gold Isolation - Point 4

**Date:** 2026-02-22
**Requirement:** Masterarbeit Punkt 4 – Output-Standardisierung + Gold-Isolation

---

## Summary

This document describes:
1. **Output standardization** for robust comparison with gold/fault lists
2. **Gold isolation** ensuring gold artifacts cannot reach reviewer context

---

## 1. Output Schema Standardization

### Schema Version

**Constant:** `DEFECT_SCHEMA_VERSION = "1.1.0"` (schemas.py)

Tracked in `RunMetadata.defect_schema_version` for every run.

### Defect Fields (Canonical Schema)

| Field | Type | Required | Validation |
|-------|------|----------|------------|
| `id` | str | Yes | Unique within run |
| `position` | str | Yes | Flagged if empty/"unknown" |
| `page_hint` | str | No | Page reference |
| `risk` | RiskLevel (A/B/C/UNK) | Yes | Enum validated |
| `fault_type` | FaultType (M/W/UNK) | Yes | Enum validated |
| `description` | str | Yes | Flagged if empty |
| `evidence` | dict | Yes | Normalized to `{quote_or_paraphrase, page_hint}` |
| `confidence` | float | Yes | Range [0.0, 1.0] |
| `flags` | List[str] | No | Auto-populated validation flags |

### Automatic Validation Flags

| Flag | Condition |
|------|-----------|
| `incomplete` | Empty evidence OR empty description |
| `missing_position` | Position is empty or "unknown" |
| `missing_description` | Description is empty |

### Normalization (Already in Pydantic)

- **Evidence**: String → `{quote_or_paraphrase: str, page_hint: null}`
- **Confidence**: Clamped to [0.0, 1.0]
- **Position/Description**: Flagged but not rejected (preserves LLM output)

---

## 2. Gold Isolation

### Defense Layers

| Layer | Location | Action |
|-------|----------|--------|
| **Load-time** | `ArtifactLoader` | LeakageGuard.validate_path() |
| **Filter-time** | `_filter_artifacts_for_reviewer()` | LeakageGuard.is_gold_path() + fail-fast |
| **Extra-context** | `_get_extra_context()` (CBR) | LeakageGuard.validate_path(checklist_path) + file type check |
| **UBR-config** | `_validate_ubr_config()` | LeakageGuard.validate_path(use_case_artifact) |
| **Metadata** | `RunMetadata.gold_guard_verified` | Verification flag |

### Fail-Fast Behavior

When gold artifact detected at reviewer level:

```python
ValueError: GOLD LEAKAGE BLOCKED: Artifact 'artifacts/gold/Faults_List.xls'
is from gold/fault directory and cannot be passed to reviewer 'reviewer_1_ubr'.
Check your config artifacts list.
```

### Metadata Tracking

```json
{
  "gold_guard_verified": true,
  "defect_schema_version": "1.1.0"
}
```

### Extra-Context Hardening (Addendum)

Gold guard now also covers `extra_config` paths:
- **CBR `checklist_path`**: Validated with LeakageGuard + restricted to `.yaml/.yml/.txt`
- **UBR `use_case_artifact`**: Validated with LeakageGuard (prevents path traversal like `../gold/...`)

Both trigger fail-fast ValueError if gold directory detected.

---

## Changed Files

| File | Change |
|------|--------|
| `src/fagan_tool/core/schemas.py` | `DEFECT_SCHEMA_VERSION`, position/description validation, new metadata fields |
| `src/fagan_tool/core/process.py` | Schema version + gold guard tracking in metadata |
| `tests/test_schemas.py` | 5 new tests for output validation |
| `tests/test_process.py` | 2 new tests for gold guard + schema version |

---

## Tests

### Output Standardization Tests

| Test | Purpose |
|------|---------|
| `test_defect_empty_position_flagged` | Empty position → `missing_position` flag |
| `test_defect_unknown_position_flagged` | "unknown" position → `missing_position` flag |
| `test_defect_empty_description_flagged` | Empty description → `missing_description` + `incomplete` |
| `test_defect_valid_fields_no_extra_flags` | Valid defect has no spurious flags |
| `test_defect_schema_version_exists` | `DEFECT_SCHEMA_VERSION` is defined |

### Gold Isolation Tests

| Test | Purpose |
|------|---------|
| `test_gold_artifact_blocked_on_reviewer_level` | Gold artifact → ValueError (fail-fast) |
| `test_gold_guard_verified_flag_set` | `_gold_guard_verified` flag is set |
| `test_schema_version_in_dry_run_metadata` | Metadata contains schema version |

---

## Compatibility

- **Existing matcher**: Uses `position`, `description`, `fault_type`, `risk` - **unchanged**
- **Existing metrics**: Uses match results - **unchanged**
- **JSON output**: Schema compatible, only new optional fields added

---

## Limitations / Open Points

1. **Validation flags are informational** - defects with flags are preserved (not rejected)
2. **Schema version** is for tracking only - no automatic migration
3. **Gold guard** depends on path naming - `artifacts/gold/` pattern

---

## Verification

- Gold standard: **UNCHANGED** (SHA256 verified)
- Matcher/Metrics: **UNCHANGED**
- All tests: **88 passed**

---

## Commit Message Template

```
feat(schemas): add output standardization and gold isolation (Point 4)

- Add DEFECT_SCHEMA_VERSION constant and metadata tracking
- Add position/description validation with flags (missing_position, missing_description)
- Add fail-fast gold guard in _filter_artifacts_for_reviewer()
- Add gold_guard_verified metadata flag
- Add 7 new tests for validation and gold isolation

Ensures robust comparison with gold list and prevents gold leakage.

Gold standard: UNCHANGED
Matcher/Metrics: UNCHANGED
```
