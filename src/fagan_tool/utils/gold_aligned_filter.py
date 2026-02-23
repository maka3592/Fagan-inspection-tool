"""Gold-aligned defect filtering for evaluation against incomplete gold standards.

When the gold standard is known to be incomplete (does not list every real defect),
unmatched novel findings inflate the false-positive count and collapse precision.

This module provides a deterministic filter that selects the subset of consolidated
defects most likely to correspond to gold-standard entries, based on:
  1. Valid position token (design section 3.x/4.x or Table reference).
  2. At least one signal token in the description.
  3. Evidence text contains at least one signal token.
  4. Description matches a gold-like defect pattern
     (missing, wrong, incorrect, inconsistent, timeout, ack, etc.).
  5. Sorted by confidence descending, capped to a configurable maximum.

The remaining defects are classified as *novel* findings -- kept in the full
``final_defects.json`` but excluded from the gold-aligned evaluation subset.
"""

import re
from typing import Dict, List

from ..core.schemas import Defect
from .position_tokens import extract_signal_tokens, has_valid_position_tokens

# Default maximum number of gold-aligned defects to emit.
DEFAULT_MAX_GOLD_ALIGNED = 12

# Gold-like description patterns (case-insensitive).
_GOLD_PATTERN = re.compile(
    r"(?i)\b("
    r"missing|misses|not\s+defined|wrong|incorrect|inconsistent"
    r"|wrong\s+occasion|ordering|timeout|ack"
    r")\b"
)


def _get_evidence_text(evidence) -> str:
    """Extract plain text from the evidence field.

    Args:
        evidence: Evidence value -- either a ``str`` or a ``dict`` with
            ``quote_or_paraphrase`` key (the canonical schema form).

    Returns:
        Plain text suitable for signal-token extraction.
    """
    if isinstance(evidence, str):
        return evidence
    if isinstance(evidence, dict):
        return evidence.get("quote_or_paraphrase", "")
    return ""


def is_gold_aligned(defect: Defect) -> bool:
    """Check whether a single defect passes all gold-aligned criteria.

    Criteria (all must hold):
      1. Position has a valid token (3.x, 4.x, or Table N).
      2. Description contains at least one signal token.
      3. Evidence text contains at least one signal token.
      4. Description matches at least one gold-like pattern.

    Args:
        defect: Consolidated defect to test.

    Returns:
        ``True`` if the defect qualifies for gold-aligned evaluation.
    """
    # 1. Valid position token
    if not has_valid_position_tokens(defect.position):
        return False

    # 2. Signal token in description
    desc_signals = extract_signal_tokens(defect.description)
    if not desc_signals:
        return False

    # 3. Signal token in evidence
    evidence_text = _get_evidence_text(defect.evidence)
    evidence_signals = extract_signal_tokens(evidence_text)
    if not evidence_signals:
        return False

    # 4. Gold-like pattern in description
    if not _GOLD_PATTERN.search(defect.description):
        return False

    return True


def filter_gold_aligned(
    defects: List[Defect],
    max_defects: int = DEFAULT_MAX_GOLD_ALIGNED,
) -> List[Defect]:
    """Return the gold-aligned subset of *defects*.

    Applies :func:`is_gold_aligned` to each defect, sorts qualifying
    defects by confidence (descending), and caps at *max_defects*.

    Args:
        defects: Full list of consolidated defects.
        max_defects: Maximum number of gold-aligned defects to return.

    Returns:
        Filtered and sorted list (may be shorter than *max_defects*).
    """
    aligned = [d for d in defects if is_gold_aligned(d)]
    aligned.sort(key=lambda d: d.confidence, reverse=True)
    return aligned[:max_defects]


def gold_aligned_summary(
    all_defects: List[Defect],
    gold_aligned: List[Defect],
    novel_sample_size: int = 20,
) -> Dict:
    """Build a summary dict suitable for persisting in meeting_output.json.

    Args:
        all_defects: Complete consolidated defect list.
        gold_aligned: Gold-aligned subset (output of :func:`filter_gold_aligned`).
        novel_sample_size: Max number of novel defect IDs to include.

    Returns:
        Dict with count fields and a sample of novel defect IDs.
    """
    aligned_ids = {d.id for d in gold_aligned}
    novel_ids = [d.id for d in all_defects if d.id not in aligned_ids]

    return {
        "total_consolidated_defects": len(all_defects),
        "total_final_defects_all": len(all_defects),
        "total_final_defects_gold_aligned": len(gold_aligned),
        "total_novel_defects": len(novel_ids),
        "novel_defect_ids_sample": novel_ids[:novel_sample_size],
    }
