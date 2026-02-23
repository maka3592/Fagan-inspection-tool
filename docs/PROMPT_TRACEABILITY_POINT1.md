# Prompt Traceability - Point 1: Literature-Based Reading Technique Instructions

**Date:** 2026-02-22
**Requirement:** Masterarbeit Punkt 1 – Literaturtreue der Reviewer-Instruktionen

---

## Summary

This document traces the changes made to reviewer prompt files to ensure they are **literature-based** and **methodologically faithful**, rather than containing generic AI heuristics or arbitrary defect quotas.

---

## Changed Files

| File | Status | Reason |
|------|--------|--------|
| `prompts/reviewer_ubr.txt` | **Updated** | UBR methodology from Petersen ESEM'08 |
| `prompts/reviewer_cbr.txt` | **Updated** | CBR methodology from Thelin PhD (Table 2.1) |
| `prompts/reviewer_pbr_user.txt` | **Updated** | PBR User perspective (Thelin framework) |
| `prompts/reviewer_pbr_tester.txt` | **Updated** | PBR Tester perspective (Thelin framework) |
| `prompts/reviewer_pbr_designer.txt` | **Updated** | PBR Designer perspective (Thelin framework) |
| `tests/test_prompt_snapshot.py` | **Updated** | Test adapted: defect quota removed per literature conformance |

---

## Literature Sources per Prompt Type

### UBR (Usage-Based Reading)

**Source:** Petersen et al., ESEM 2008 + Use-Case Task Notation

**Core methodology implemented:**
1. Start with highest-priority use case
2. Trace through artifact following Tasks
3. Verify completeness/correctness for use case goal
4. Record defects where artifact fails to support use case
5. Proceed to next use case in priority order

**Variants supported:**
- **RB-UBR** (Rank-Based): Work through all prioritized use cases
- **TC-UBR** (Time-Constrained): Respect time budgets per use case if provided

**Removed:**
- Arbitrary defect quotas ("Find 6-12 defects")
- Static section focus as mandatory (3.x/4.x as absolute requirement)
- Generic cross-reference heuristics not tied to use-case tracing

**Preserved:**
- JSON output schema
- Position format (canonical tokens)
- Evidence requirements
- Signal-name-first description style

---

### CBR (Checklist-Based Reading)

**Source:** Thelin PhD Thesis, Table 2.1 (18-Item Checklist)

**Core methodology implemented:**
- Systematic checklist-driven inspection
- Three dimensions: Consistency, Correctness, Completeness
- 18-item reference structure (Modules, Signals/Parameters, MSCs, Introductory Text)
- Project-provided checklist takes precedence; Thelin items as fallback

**Removed:**
- Arbitrary defect quotas ("Find 4-6 defects per reviewer")
- Non-literature-based additional heuristics

**Preserved:**
- JSON output schema
- Position format
- Evidence requirements
- Optional `checklist_item` field for traceability

---

### PBR (Perspective-Based Reading)

**Source:** Thelin PhD Thesis (Framework, not historical Basili/Shull scripts)

**Transparency Note:** Each PBR prompt explicitly states it is a "Thelin-based PBR framework, not a complete historical original role script."

**Perspectives and Models:**

| Perspective | Model | Focus |
|-------------|-------|-------|
| User | Use Cases | Trace user scenarios through design |
| Tester | Equivalence Partitioning | Partition inputs/outputs, check coverage |
| Designer | Structured Analysis | Decompose modules, interfaces, data flows |

**Removed:**
- Generic UX/accessibility/performance checklists (User)
- Broad "testability" checklists without method (Tester)
- Vague "implementability" questions without structure (Designer)
- UNK allowed for risk/fault_type (now prohibited)

**Added:**
- Explicit JSON output schema (was missing in PBR prompts)
- Canonical position format
- Evidence requirements
- Signal-name-first description style

---

## Comparability Principle

The updated prompts align with the thesis requirement for **fair comparison** with historical manual inspections:

1. **No unfair advantages**: No artificial defect quotas or AI-specific heuristics
2. **Method-faithful**: Each technique follows its documented methodology
3. **Transparent limitations**: PBR explicitly notes framework vs. original scripts
4. **Consistent output**: All prompts use the same JSON schema and position format

---

## Limitations

1. **PBR**: Only Thelin-based framework implemented, not complete historical Basili/Shull role scripts (not available in repository)
2. **UBR**: Requires prioritized use cases in input; if missing, reviewer must note transparency
3. **CBR**: Falls back to Thelin 18-item checklist if no project checklist provided

---

## Verification

- Gold standard files **NOT modified** (checksum verification required)
- JSON output schema **unchanged** (defects[], notes, all mandatory fields)
- Python `.format()` compatibility **preserved** ({extra_context} placeholder retained)
- Leakage guard **not affected**

---

## Note on Result Changes

Any changes to inspection results (defect counts, precision, recall) caused by these prompt modifications must be:
1. Documented in commit messages
2. Attributed to methodology alignment, not arbitrary tuning
3. Evaluated through the standard manual validation workflow

---

## Commit Message Template

```
refactor(prompts): align reviewer prompts with literature-based reading techniques

- UBR: Petersen ESEM'08 methodology (use-case driven, RB/TC variants)
- CBR: Thelin PhD Table 2.1 (18-item checklist, CCC dimensions)
- PBR: Thelin framework (User/Tester/Designer perspectives with models)

Removed:
- Arbitrary defect quotas
- Non-method-based heuristics

Added:
- Literature citations in prompts
- Transparency notes for PBR limitations
- Consistent JSON schema across all PBR prompts

Gold standard: UNCHANGED
Eval/Matcher: UNCHANGED
```
