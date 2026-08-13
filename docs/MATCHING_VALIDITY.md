# Matching Validity & Evaluation Rationale

This document explains the matching algorithm, its gates and heuristics,
why the metrics are stable and reproducible, and how to perform manual
validation as a methodological safeguard.

---

## 1. How Matching Works (Gate Sequence)

The `DefectMatcher._calculate_similarity()` method applies gates in
sequence. A candidate (found, gold) pair is rejected (score = 0.0) if
any gate fails. Only candidates that pass all gates receive a combined
similarity score.

### Gate 1: Position Overlap

- **Input**: Union of position tokens from `position`, `original_position`,
  and `position_canonical` (found) vs. tokens from `position` (gold).
- **Rule**: At least one token must appear in both sets.
- **Rationale**: Position is the strongest structural anchor. Different
  sections are different defects.

### Gate A3: Conservative Multi-Position Filter

- **Condition**: Gold has >= 2 position tokens AND overlap < 2 AND no
  signal confirmation.
- **Rule**:
  - If gold has a single most-specific token (highest granularity, e.g.,
    `3.4.2` beats `3.2`), matching it suffices.
  - If gold has >= 3 same-granularity tokens and overlap < 2, reject.
- **Rationale**: Multi-position gold defects span multiple sections.
  Overlapping only one low-specificity token is likely coincidental.
  Signal confirmation (shared signal or >= 2 domain sub-tokens) overrides
  this gate because it provides an independent anchor.

### Gate 2: Signal Token Constraint

- **Input**: Signal tokens extracted from descriptions (and evidence for
  found defects). Includes quoted names, underscore-separated names,
  CamelCase names, and topic prefixes (1-4 words before the first period).
- **Rules**:
  - **Both sides have signals**: Must share an exact signal token OR >= 2
    domain sub-tokens (signal names split at underscores).
  - **Only one side has signals**: The other side's description is checked
    for domain sub-tokens. If none overlap, the final score is dampened
    by 25%.
  - **Neither side has signals**: Proceeds to Gate 3.
- **Rationale**: Signal names are the strongest semantic anchors in this
  domain. Two defects naming different signals at the same position are
  about different things.

### Gate 3: High Description Similarity Requirement

- **Condition**: Neither side has signal tokens.
- **Rule**: Description similarity (rapidfuzz `token_sort_ratio`) must
  be >= 0.80.
- **Rationale**: Without signal anchors, position overlap alone is
  insufficient. Only very similar descriptions justify a match.

### Scoring

If all gates pass, the combined score is:

```
score = pos_sim * 0.30 + desc_sim * 0.60 + risk_bonus + type_bonus
      + feature_bonus
score *= dampening_factor  (0.75 if one-side-signal without domain overlap)
```

Where:
- `pos_sim`: Overlap Coefficient = |A ∩ B| / min(|A|, |B|)
- `desc_sim`: `rapidfuzz.fuzz.token_sort_ratio() / 100`
- `risk_bonus`: +0.05 if risk levels match
- `type_bonus`: +0.05 if fault types match
- `feature_bonus`: ±0.05 max, based on shared/contradictory feature
  keywords (missing, ack, timeout, parameter, etc.) — only when both
  sides have feature keywords

### Match Classification

| Score Range          | Match Type |
|----------------------|------------|
| >= `exact_threshold` (0.85) | EXACT |
| >= `match_threshold` (0.60 default) | PARTIAL |
| < `match_threshold`  | NO_MATCH  |

---

## 2. Why TP/FP Are Classified This Way

### True Positives (TP)

A defect is TP when it matches a gold defect with:
- **Shared position token(s)** — structural anchor
- **Shared signal token(s)** — semantic anchor (when available)
- **Similar normalized description** — content confirmation

All three layers must align. This makes TP robust and defensible.

### False Positives (FP)

FP defects fall into two categories:
- **Novel findings**: High-confidence defects not in the gold standard.
  These may be genuine issues the gold standard missed. They are classified
  as `NO_MATCH_POTENTIAL_NEW`.
- **Generic patterns**: Low-confidence defects or those with generic
  descriptions ("missing signal", "wrong parameters") that happen to share
  a position with a gold defect but differ on signal or description.

### Why False Partials Are Prevented

Before the signal gating improvements, defects like `Order_Reject` and
`Bill` could match because:
- They shared a position (e.g., 3.2.1)
- Descriptions had high token overlap ("signal is missing")

Now, the signal gate requires that named signals actually match. Domain
sub-tokens provide a secondary check (e.g., `order_reject` and
`reject_order` share both "order" and "reject").

---

## 3. Why These Heuristics Are Stable

1. **Deterministic**: No randomness, no LLM calls during evaluation.
   Same inputs always produce same outputs.
2. **Configurable**: `--match-threshold` controls strictness.
   Signal gating is structural (based on extracted tokens, not scores).
3. **Debug exports**: `match_debug.jsonl` logs per-candidate diagnostics
   including position overlap count, signal overlap count, extracted
   signals, normalized description tokens, feature flags, and gate
   outcomes. Enable with `FAGAN_MATCH_DEBUG=1` or provide `--output`.
4. **Reproducible**: Run folders preserve all inputs and outputs.
   Re-running `fagan eval --run <ID>` produces identical results.

---

## 4. Threshold Configuration and Experimental Use

The technical CLI default for `--match-threshold` is **0.60**.

The final main evaluation uses a threshold of **0.65**. The value
**0.60** is additionally considered as a sensitivity threshold. The
technical CLI default is distinct from this final evaluation decision.

The signal gates already reject most false partials at the gate level
(score = 0.0).

---

## 5. Manual Validation Workflow

Automated matching is a heuristic. Manual validation is methodologically
necessary to confirm TP/FP classifications and guard against optimism.

### Step 1: Generate Manual Template

```bash
fagan manual-template --run <RUN_ID>
```

This creates `eval/<RUN_ID>/matches_manual.csv` from `matches_enriched.csv`,
adding columns:
- `manual_is_true_match`: Set to `TRUE` or `FALSE` for each match.
- `manual_notes`: Free-text annotation.

### Step 2: Review and Annotate

Open the CSV in a spreadsheet editor. For each EXACT/PARTIAL match:
- Read the found description, gold description, and similarity score.
- Decide: Is this a genuine match (`TRUE`) or a false match (`FALSE`)?
- Add notes explaining your reasoning.

### Step 3: Calculate Manual Metrics

```bash
fagan manual-eval --run <RUN_ID>
```

This produces `eval/<RUN_ID>/metrics_manual.json` with precision, recall,
and F1 based on your manual annotations instead of the automated matching.

### Automatic Candidates and Manual Validation

| Metric Source | Based On | Use Case |
|---------------|----------|----------|
| `metrics.json` | Automated heuristic matching | Rapid iteration, CI |
| `metrics_manual.json` | Human expert annotations | Thesis reporting, validation |

The matcher produces match candidates. Manual assessment determines the
confirmed assignment. For the final pooled evaluation, the finalized
manual validation decisions are authoritative.

---

## 6. Debug Export Format

When `FAGAN_MATCH_DEBUG=1` is set or `--output` is provided, the matcher
writes `match_debug.jsonl` with one JSON object per candidate pair:

```json
{
  "found_id": "F1",
  "gold_id": "G5",
  "found_tokens": ["3.2.1"],
  "gold_tokens": ["3.2.1", "3.4.2"],
  "position_overlap_count": 1,
  "signal_overlap_count": 0,
  "extracted_signals_found": ["reject_order"],
  "extracted_signals_gold": ["start_alarm"],
  "normalized_desc_tokens_found": 8,
  "normalized_desc_tokens_gold": 6,
  "feature_flags_found": ["missing", "signal"],
  "feature_flags_gold": ["missing", "alarm"],
  "combined_score": 0.0,
  "reason": "no_signal_overlap"
}
```

Up to 50 records are written, sorted by score descending.
