# Reviewer Input Assignment - Point 3

**Date:** 2026-02-22
**Requirement:** Masterarbeit Punkt 3 – Reviewer-spezifische Dokumentzuweisung

---

## Summary

This document describes the implementation of **reviewer-specific artifact assignment**, ensuring each reviewer type receives only methodologically appropriate documents instead of blindly receiving all artifacts.

---

## Problem Statement (Before)

- All reviewers received identical artifacts (no filtering)
- No validation that required artifacts were present
- No methodological conformance (e.g., PBR_DESIGNER getting use cases)
- Leakage guard only at load time, not at reviewer level

---

## Solution (After)

### Central Artifact Policy

**Location:** `src/fagan_tool/core/schemas.py` → `REVIEWER_ARTIFACT_POLICY`

Each reading technique defines:
- `required_types`: Must be present (fail-fast if missing)
- `optional_types`: Allowed but not mandatory
- `forbidden_types`: Additional restrictions beyond gold guard

### Artifact Types

Types are inferred from path/filename by `ArtifactLoader._infer_type()`:

| Type | Path Pattern |
|------|--------------|
| `design` | `design/`, `stldd` |
| `usecase` | `usecase/`, `use_case` |
| `requirements` | `requirement/`, `req` |
| `checklist` | `checklist/`, `cbr_checklist` |
| `guide` | `guide/`, `ubr`, `pbr` |

---

## Reviewer Artifact Policies

| Technique | Required | Optional | Notes |
|-----------|----------|----------|-------|
| **UBR** | design | usecase, guide, requirements | Use-case-driven inspection |
| **CBR** | design | checklist, usecase, requirements | Checklist-based |
| **PBR_TESTER** | design | requirements, usecase | Testability focus |
| **PBR_DESIGNER** | design | requirements | Implementability focus |
| **PBR_USER** | design | usecase, requirements | User-scenario focus |

---

## Validation Rules

### Fail-Fast on Missing Required Artifacts

```python
# ValueError raised if required artifacts missing
ValueError: Reviewer reviewer_1_ubr (UBR) missing required artifact types: design.
Found: usecase. Check your config artifacts list.
```

### Defensive Gold Guard on Reviewer Level

Even if a gold artifact somehow reaches `_filter_artifacts_for_reviewer()`, it is blocked:

```python
# Console warning + artifact rejected
⚠ BLOCKED: Gold artifact 'artifacts/gold/Faults_List.xls' rejected for reviewer_1_ubr
```

---

## Metadata Tracking

**New field in `RunMetadata`:** `reviewer_artifacts_assigned`

```json
{
  "reviewer_artifacts_assigned": {
    "reviewer_1_ubr": ["design/Taxi_des_exp_v2.pdf", "usecases/UseCasesRank_v3.4.pdf"],
    "reviewer_2_ubr": ["design/Taxi_des_exp_v2.pdf", "usecases/UseCasesRank_v3.4.pdf"],
    "reviewer_3_ubr": ["design/Taxi_des_exp_v2.pdf", "usecases/UseCasesRank_v3.4.pdf"]
  }
}
```

---

## Changed Files

| File | Change |
|------|--------|
| `src/fagan_tool/core/schemas.py` | Added `REVIEWER_ARTIFACT_POLICY`, `reviewer_artifacts_assigned` |
| `src/fagan_tool/core/process.py` | Added `_filter_artifacts_for_reviewer()`, metadata tracking |
| `tests/test_process.py` | Added `TestReviewerArtifactAssignment` (7 tests) |

---

## Tests

| Test | Purpose |
|------|---------|
| `test_ubr_requires_design` | UBR gets design artifact |
| `test_ubr_missing_design_raises_error` | Missing required → ValueError |
| `test_cbr_requires_design` | CBR gets design + checklist |
| `test_pbr_tester_requires_design` | PBR_TESTER gets design + requirements |
| `test_pbr_designer_filters_usecase` | PBR_DESIGNER does NOT get usecase |
| `test_gold_artifact_blocked_on_reviewer_level` | Gold blocked even if passed in |
| `test_artifact_policy_exists_for_all_techniques` | All techniques have policy |

---

## Limitations / Open Points

1. **Artifact type inference** depends on path naming conventions
2. **No per-reviewer artifact override** in config (all reviewers of same technique get same filtering)
3. **Checklist** for CBR is optional (loads via `checklist_path` in extra_config, not artifacts list)

---

## Verification

- Gold standard: **UNCHANGED** (SHA256 verified)
- Defect JSON schema: **UNCHANGED**
- Existing tests: **81 passed**

---

## Commit Message Template

```
feat(process): implement reviewer-specific artifact assignment (Point 3)

- Add REVIEWER_ARTIFACT_POLICY with required/optional/forbidden types
- Add _filter_artifacts_for_reviewer() for technique-based filtering
- Add defensive gold guard on reviewer level
- Track reviewer_artifacts_assigned in RunMetadata
- Add 7 tests for artifact assignment validation

Ensures methodological conformance: each reviewer type receives
only appropriate documents (e.g., PBR_DESIGNER does not get use cases).

Gold standard: UNCHANGED
```
