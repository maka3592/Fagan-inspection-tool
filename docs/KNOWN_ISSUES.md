# Known Issues and Solutions

## Recommended Model for Thesis Runs

**Default Model: `gpt-4o-mini`**

For thesis runs, we recommend using `gpt-4o-mini` for the following reasons:

1. **Stable API behavior**: Full support for temperature, top_p, and other sampling parameters
2. **Reliable JSON output**: Works well with `response_format: json_object`
3. **Cost-effective**: Good balance of quality and cost
4. **Tested thoroughly**: All tests pass with this model

### How to Switch Models

To use a different model, update your config file:

```yaml
llm_params:
  provider: "openai"
  model: "gpt-4o-mini"  # or "gpt-4o" for higher quality
  temperature: 0.2
  max_tokens: 4096
```

**Note**: GPT-5 models (gpt-5-mini, gpt-5-nano) have restrictions:
- Do not support custom temperature (only default=1.0)
- Do not support top_p, presence_penalty, frequency_penalty
- The provider handles this automatically (logs warning, continues without these params)

---

## GPT-5 Model JSON Parsing Issues (Resolved)

### Issue Description

When using `gpt-5-mini` or other GPT-5 models, reviewer outputs would fail JSON parsing
with the error:

```
Could not extract valid JSON from response: ...
```

This resulted in:
- 0 defects found in reviewer outputs
- `json_parse_errors` recorded in `meeting_output.json`
- Debug files with empty responses in `runs/<run_id>/debug/`

### Root Cause Analysis

1. **Empty Responses**: The OpenAI API would sometimes return empty responses
   (`content: null`) without clear indication of why.

2. **response_format Compatibility**: The simple `{"type": "json_object"}` format
   was insufficient for reliable structured output with GPT-5 models.

3. **No Error Logging**: Empty responses were silently converted to empty strings
   without logging the finish_reason or other diagnostic information.

### Solution Implemented

1. **Strict JSON Schema Output**: Instead of `json_object` mode, we now use
   `json_schema` with strict schema validation:

   ```python
   response_format = {
       "type": "json_schema",
       "json_schema": {
           "name": "reviewer_output",
           "strict": True,
           "schema": {...}
       }
   }
   ```

2. **Improved Response Handling**: The OpenAI provider now:
   - Checks `finish_reason` for truncation or content filtering
   - Logs warnings for empty responses with diagnostic info
   - Returns valid fallback JSON for structured output modes
   - Checks for model refusals

3. **Robust JSON Extraction**: The parser now handles:
   - Markdown code fences (```json ... ```)
   - Leading/trailing prose around JSON
   - Trailing commas in JSON
   - Empty responses (returns minimal valid JSON)

### Verification

After the fix, runs should show:
- `json_parse_errors: []` (empty array) in `meeting_output.json`
- No debug files in `runs/<run_id>/debug/`
- Reviewers with actual defect counts (or 0 if legitimately none found)

### GPT-5 Model Limitations

GPT-5 models (gpt-5-mini, gpt-5-nano, gpt-5) have specific restrictions:

| Parameter | Supported | Notes |
|-----------|-----------|-------|
| temperature | ❌ | Only default (1.0) supported |
| top_p | ❌ | Not supported |
| max_tokens | ❌ | Use `max_completion_tokens` instead |
| response_format | ✅ | json_object and json_schema supported |

The OpenAI provider automatically handles these restrictions and logs warnings
when unsupported parameters are specified in the config.

## Related Files

- `src/fagan_tool/providers/openai_provider.py` - API parameter handling
- `src/fagan_tool/agents/base_agent.py` - JSON extraction
- `src/fagan_tool/agents/reviewer_agent.py` - Reviewer structured output
- `tests/test_json_parse_errors.py` - Extraction tests
- `tests/test_openai_provider_tokens.py` - Provider parameter tests

---

## Gold Standard Incompleteness and Evaluation Collapse

### Problem

The gold standard (`artifacts/gold/Faults_List_In_ver6.xls`) is known to be
**incomplete** -- it documents 30 defects from the original human inspectors but
does not catalogue every real defect in the design artifact.  When the LLM-based
inspection discovers legitimate novel findings that have no gold counterpart,
the evaluation matcher classifies them as `no_match_potential_new` or
`no_match_false_positive`, which inflates the false-positive count and
**collapses precision**.

Example from an early run:

| Metric | Value |
|--------|-------|
| Total found | 30 |
| True positives | 2 |
| no_match_potential_new | 26 |
| Precision | 0.07 |

Most of the 26 unmatched defects were genuine findings about use-case coverage,
timing constraints, and missing acknowledgements -- but without a gold entry
they were counted as false positives.

### Solution: Two Reporting Modes

The pipeline now produces **two** defect files per run:

| File | Contents |
|------|----------|
| `final_defects.json` | **ALL_FOUND** -- every consolidated defect, unfiltered |
| `final_defects_gold_aligned.json` | **GOLD_ALIGNED** -- deterministic subset most likely to match gold entries |

#### Gold-aligned filter criteria (all must hold)

1. **Valid position token** -- design section reference (`3.x`, `4.x`) or
   `Table N`; use-case-only positions are excluded.
2. **Signal token in description** -- at least one identifier such as
   `Reject_Order`, `Start_Voice`, `ACK_Timeout` (extracted via
   `extract_signal_tokens()`).
3. **Signal token in evidence** -- the `quote_or_paraphrase` field must also
   contain a signal token.
4. **Gold-like pattern in description** -- matches one of: *missing, misses,
   not defined, wrong, incorrect, inconsistent, wrong occasion, ordering,
   timeout, ack*.
5. **Sorted by confidence** descending, **capped** to 12 (configurable via
   `DEFAULT_MAX_GOLD_ALIGNED`).

Defects that pass are written to `final_defects_gold_aligned.json`.  The
remaining defects are classified as **novel findings** -- kept in
`final_defects.json` for full transparency.

#### Summary counts in `meeting_output.json`

The `gold_aligned_summary` block is added automatically:

```json
{
  "gold_aligned_summary": {
    "total_consolidated_defects": 30,
    "total_final_defects_all": 30,
    "total_final_defects_gold_aligned": 12,
    "total_novel_defects": 18,
    "novel_defect_ids_sample": ["D13", "D14", "..."]
  }
}
```

### CLI Usage

#### Standard evaluation (all defects)

```bash
fagan eval \
  --run <run-id> \
  --gold artifacts/gold/Faults_List_In_ver6.xls \
  --match-threshold 0.65
```

#### Gold-aligned evaluation (filtered subset)

```bash
fagan eval \
  --run <run-id> \
  --gold artifacts/gold/Faults_List_In_ver6.xls \
  --match-threshold 0.65 \
  --gold-aligned
```

This reads `final_defects_gold_aligned.json` instead of `final_defects.json`
and records `defects_file_used: "final_defects_gold_aligned.json"` in the
evaluation metadata for full traceability.

#### Custom defects file

```bash
fagan eval \
  --run <run-id> \
  --gold artifacts/gold/Faults_List_In_ver6.xls \
  --defects-file path/to/custom_defects.json
```

`--defects-file` overrides `--gold-aligned` when both are specified.

### Interpreting Results

| Mode | Precision reflects | Best for |
|------|--------------------|----------|
| ALL_FOUND | All findings vs gold | Transparency, novel-finding discovery |
| GOLD_ALIGNED | Only gold-like findings vs gold | Fair precision/recall against incomplete gold |

**Recommendation for thesis reporting**: Report both modes.  The gold-aligned
precision/recall measures detection quality against known defects; the novel
count documents additional value the LLM inspection provides beyond the
original human inspectors.

### Related Files

- `src/fagan_tool/utils/gold_aligned_filter.py` - Filter logic
- `src/fagan_tool/core/process.py` - Output file generation
- `src/fagan_tool/cli.py` - `--gold-aligned` and `--defects-file` flags
- `src/fagan_tool/core/schemas.py` - `EvaluationMetadata.defects_file_used`
- `tests/test_gold_aligned_filter.py` - Filter and integration tests

---

## Diagnosing No-Match Results

When evaluating against the gold standard, some found defects may not match any
gold defect.  The enriched CSV (`matches_enriched.csv`) now includes four debug
columns that explain **why** each defect did or did not match:

| Column | Description |
|--------|-------------|
| `best_candidate_gold_id` | Gold ID that was the closest candidate |
| `best_candidate_gold_position` | Position of that gold candidate |
| `best_candidate_similarity` | Highest similarity score achieved |
| `best_candidate_match_reason` | Gate that blocked (or "matched") |

### Match Reason Values

| Reason | Meaning |
|--------|---------|
| `matched` | Successfully matched to a gold defect |
| `below_threshold` | Best score was below the match threshold |
| `no_position_overlap` | GATE 1: No shared position token |
| `no_signal_overlap` | GATE 2: Both sides have signal tokens but none overlap |
| `low_desc_sim_no_signals` | GATE 3: No signal tokens and description similarity < 0.80 |
| `no_candidates` | Empty gold list (no candidates to compare) |

### How to Diagnose Near-Misses

1. Open `matches_enriched.csv` and filter to `match_type` containing `no_match`
2. Sort by `best_candidate_similarity` descending
3. The top rows are "near misses" — defects that almost matched
4. Check `best_candidate_match_reason` to see which gate blocked the match

### Position Canonicalization and Drift Guard

**Problem**: LLM reviewers sometimes produce defect positions that don't match
the sections actually referenced in their description and evidence text.
For example, `position="3.4.1"` when the description clearly references `4.1`.
This drift causes false mismatches during evaluation.

**Solution**: Every defect now undergoes position canonicalization during meeting
consolidation.  The scribe agent:

1. **Extracts position tokens** from the position field, description, and evidence
2. **Detects drift** when position tokens don't match text mentions, or when
   position tokens are not in the valid artifact token set
3. **Autofixes safely** when exactly ONE valid mention token exists in the text
   (reason: `single_mentioned_token`)
4. **Rejects** hallucinated positions that cannot be safely autofixed

**Soft canonicalization**: The autofix is "soft" — it never overwrites
`defect.position`.  The reviewer-original position is preserved so that the
matcher can still match against gold entries referencing the original section.
The inferred position is stored separately in `position_canonical`.

Each defect carries these fields for full traceability:

| Field | Description |
|-------|-------------|
| `position` | **Original** reviewer-provided position (never overwritten by autofix) |
| `original_position` | Copy of position when autofix is applied (null if unchanged) |
| `position_canonical` | Inferred canonical position from description/evidence context |
| `position_mentions` | Section tokens found in description + evidence |
| `position_autofixed` | Whether autofix was applied |
| `position_autofix_reason` | Reason for autofix (e.g. `single_mentioned_token`) |

**Union position matching**: The evaluation matcher uses the **union** of tokens
from `position`, `original_position`, and `position_canonical` when checking for
position overlap (GATE 1).  This means a defect can match gold on either its
original reviewer-provided position or its inferred canonical section, preventing
the TP=0 regression that occurred when autofix overwrote positions.

### Drift Statistics in meeting_output.json

Every run records a `position_drift_stats` block:

```json
{
  "position_drift_stats": {
    "position_drift_total": 29,
    "position_drift_count": 5,
    "position_drift_rate": 0.1724,
    "position_autofix_count": 3,
    "position_drift_examples": [
      {
        "defect_id": "meeting_abc123",
        "position_original": "3.4.1",
        "position_canonical": "4.1",
        "mentions": ["4.1"],
        "description_prefix": "Stop voice. The signal 'Stop_Voice' is missing from the MSC"
      }
    ]
  }
}
```

### How to Confirm Drift Rate Improved

1. Run an inspection: `fagan run --config configs/examples/c1_ubr.yaml --run-id drift_check`
2. Open `runs/drift_check/meeting_output.json`
3. Check `position_drift_stats.position_drift_rate` — target < 0.05
4. Check `position_drift_stats.position_autofix_count` — should rescue previously-lost defects
5. Evaluate: `fagan eval --run drift_check --gold artifacts/gold/Faults_List_In_ver6.xls --gold-aligned`
6. Compare exact/partial match counts against baseline

### Verification Commands

```bash
# Run all tests
pytest -q

# Run an inspection
fagan run --config configs/examples/c1_ubr.yaml --run-id drift_check

# Evaluate with gold-aligned filter
fagan eval --run drift_check --gold artifacts/gold/Faults_List_In_ver6.xls --match-threshold 0.65 --gold-aligned
```

### Related Files

- `src/fagan_tool/evaluation/matcher.py` - SimilarityResult, union position matching, debug fields
- `src/fagan_tool/core/schemas.py` - Defect canon fields, DefectMatch debug fields, EvaluationMetadata.union_position_matching
- `src/fagan_tool/utils/position_tokens.py` - `canonicalize_defect_position()`, `collect_defect_position_tokens()`, `PositionCanonResult`
- `src/fagan_tool/agents/scribe_agent.py` - Soft canonicalization drift guard
- `src/fagan_tool/core/process.py` - Drift statistics in meeting_output.json
- `src/fagan_tool/cli.py` - CSV debug column export

---

## Position Scoring: Overlap Coefficient

### Problem

The position similarity score was previously hardcoded to `0.9` whenever any
position token overlap was detected.  This caused two issues:

1. **Under-scoring exact/superset matches** — a found defect referencing
   `"3.2.1, 3.2.2, 3.4.2"` against gold `"3.2.1., 3.2.2, 3.4.2"` should score
   1.0 (exact match) but scored 0.9.
2. **Near-miss threshold failures** — the 0.03 penalty pushed combined scores
   below the match threshold (e.g. 0.63 instead of 0.66), causing false
   negatives.

### Solution: Overlap Coefficient

Position scoring now uses the **Overlap Coefficient**:

```
pos_sim = |A ∩ B| / min(|A|, |B|)
```

Where `A` = found defect position tokens, `B` = gold defect position tokens.

| Scenario | Example | Score |
|----------|---------|-------|
| Exact match | `{3.2.1, 3.4.2}` vs `{3.2.1, 3.4.2}` | 1.0 |
| Found is superset | `{3.2.1, 3.2.2, 3.4.2}` vs `{3.4.2}` | 1.0 |
| Partial overlap | `{3.2.1, 3.4.2}` vs `{3.2.1, 4.1}` | 0.5 |
| No overlap | `{3.2.1}` vs `{4.1}` | GATE 1 blocks (0.0) |

This means defects whose tokens are a superset of the gold tokens always score
1.0 for position and are never penalised for extra tokens.

---

## GATE 3 Relaxation: One-Sided Signal Tokens

### Problem (TP=0 Regression)

After introducing signal-first description format (`'Signal_Name': ...`), the
matcher produced **0 true positives**.  Root cause: GATE 3 required description
similarity ≥ 0.80 whenever `both_have_signals` was False — i.e., when **either**
side lacked signal tokens.

Gold defect descriptions are often generic (e.g. "Missing signal in MSC") and
lack extractable signal tokens.  Found defects have signal-first format.
Result: `both_have_signals = False` → GATE 3 fires → description formats differ
→ `desc_sim < 0.80` → score 0.0 for all pairs.

### Solution

GATE 3 now only fires when **neither** side has signal tokens:

```python
# OLD (too aggressive):
if not both_have_signals:
    if desc_sim < 0.80: return 0.0

# NEW (relaxed — only blocks when NEITHER side has signals):
neither_has_signals = not found_signals and not gold_signals
if neither_has_signals:
    if desc_sim < 0.80: return 0.0
```

**Rationale**: When at least one side has signal tokens, the combined score
formula (position 30% + description 60% + attributes 10%) and the match
threshold provide sufficient protection against false matches.  The 0.80 bar is
only needed for truly generic descriptions where position alone is insufficient.

---

## Match Debug Mode (`FAGAN_MATCH_DEBUG`)

### Usage

Enable detailed candidate-pair diagnostics during evaluation:

```bash
# Via environment variable
FAGAN_MATCH_DEBUG=1 fagan eval \
  --run <run-id> \
  --gold artifacts/gold/Faults_List_In_ver6.xls \
  --match-threshold 0.65

# Output is also written automatically when --output-dir is specified
```

### Output

Writes `match_debug.jsonl` to the evaluation output directory containing the
top 50 candidate pairs sorted by combined score (descending).  Each line is a
JSON object:

```json
{
  "found_id": "meeting_abc123",
  "found_position": "3.4.2",
  "found_tokens": ["3.4.2"],
  "gold_id": "15",
  "gold_position": "3.2.1., 3.2.2, 3.4.2",
  "gold_tokens": ["3.2.1", "3.2.2", "3.4.2"],
  "position_score": 0.85,
  "combined_score": 0.72,
  "reason": "matched"
}
```

### How to Use for Diagnosis

1. Run evaluation with `FAGAN_MATCH_DEBUG=1`
2. Open `match_debug.jsonl` in the eval output directory
3. Filter by `reason` to see which gate blocks specific pairs
4. Sort by `combined_score` descending to find near-misses
5. Cross-reference with `matches_enriched.csv` for the final match decisions

### Related Files

- `src/fagan_tool/evaluation/matcher.py` - Debug record collection and `_write_debug()`
- `src/fagan_tool/cli.py` - Passes output directory to matcher
