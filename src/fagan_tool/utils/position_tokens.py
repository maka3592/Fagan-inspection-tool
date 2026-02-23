"""Canonical position token and signal token extraction and comparison utilities.

This module provides utilities for extracting, canonicalizing, and comparing
position tokens from defect positions. It ensures consistent position handling
across reviewers, meeting consolidation, and matching.

Position tokens include:
- Section numbers: 3.1, 3.2.1, 4.2, etc.
- Table references: Table 1, Table 2, etc.

Signal tokens include:
- Quoted names: 'Reject_Order', "Logged In"
- Underscore-separated names: Start_Voice, Voice_msg
- CamelCase names: OrderOper, LoginOk
"""

import re
from dataclasses import dataclass, field
from typing import List, Optional, Set, Tuple


# Regex patterns for position tokens
# Section pattern: must start with 3 or 4 (design sections), not preceded by "case"
# Valid: 3.1, 3.4.2, 4.1, 4.2.1
# Invalid: 1.1 (not in design scope), numbers after "use case"
SECTION_PATTERN = re.compile(r'\b([34]\.\d+(?:\.\d+)?)\b')
TABLE_PATTERN = re.compile(r'\btable\s*(\d+)\b', re.IGNORECASE)
# Pattern to detect "use case X.Y" - should not extract the X.Y as section
USE_CASE_NUMBER_PATTERN = re.compile(r'\buse\s*case\s*\d+(?:\.\d+)?\b', re.IGNORECASE)


def extract_position_tokens(text: str) -> List[str]:
    """Extract canonical position tokens from text.

    Extracts:
    - Section tokens: 3.1, 3.2.1, 4.2, etc.
    - Table tokens: "Table 1", "Table 2", etc.

    Args:
        text: Position text to parse (e.g., "Section 3.4.1, Table 1")

    Returns:
        List of unique tokens in stable sorted order (Tables first, then sections numerically).
        Empty list if no valid tokens found.

    Examples:
        >>> extract_position_tokens("Section 4.1")
        ['4.1']
        >>> extract_position_tokens("3.3.2, 3.1")
        ['3.1', '3.3.2']
        >>> extract_position_tokens("Table 1, 3.4.2")
        ['Table 1', '3.4.2']
        >>> extract_position_tokens("Use Case 1.1")
        []
    """
    if not text:
        return []

    tokens: Set[str] = set()

    # Extract table references first
    for match in TABLE_PATTERN.finditer(text):
        table_num = match.group(1)
        tokens.add(f"Table {table_num}")

    # Extract section numbers
    for match in SECTION_PATTERN.finditer(text):
        section = match.group(1)
        tokens.add(section)

    # Sort: Tables first (alphabetically), then sections (by numeric parts)
    def sort_key(token: str):
        if token.startswith("Table"):
            # Tables sort first, by number
            num = int(token.split()[1])
            return (0, num, "")
        else:
            # Sections sort by numeric parts
            parts = [int(p) for p in token.split(".")]
            return (1, parts[0], parts[1] if len(parts) > 1 else 0, parts[2] if len(parts) > 2 else 0)

    return sorted(tokens, key=sort_key)


def canonicalize_position(text: str) -> str:
    """Convert position text to canonical token format.

    Takes any position text and returns a canonical representation
    using only the extracted tokens, joined by ", ".

    Args:
        text: Position text to canonicalize

    Returns:
        Canonical position string (e.g., "Table 1, 3.4.2") or "" if no tokens found.

    Examples:
        >>> canonicalize_position("Section 3.4.1")
        '3.4.1'
        >>> canonicalize_position("Table 1 and Section 3.4.2")
        'Table 1, 3.4.2'
        >>> canonicalize_position("Use Case 1.1")
        ''
    """
    tokens = extract_position_tokens(text)
    return ", ".join(tokens)


def shares_position_token(a: str, b: str) -> bool:
    """Check if two position strings share at least one exact token.

    This is a strict comparison - tokens must match exactly.
    No prefix matching, no substring matching.

    Args:
        a: First position string
        b: Second position string

    Returns:
        True if at least one token appears in both positions.

    Examples:
        >>> shares_position_token("3.4.1", "Section 3.4.1, 3.4.2")
        True
        >>> shares_position_token("3.1", "3.2.1")
        False
        >>> shares_position_token("Table 1", "Table 1, 3.4.2")
        True
        >>> shares_position_token("4.1", "4.2")
        False
    """
    tokens_a = set(extract_position_tokens(a))
    tokens_b = set(extract_position_tokens(b))

    # Empty token sets never share
    if not tokens_a or not tokens_b:
        return False

    return bool(tokens_a & tokens_b)


def collect_defect_position_tokens(
    position: str,
    original_position: Optional[str] = None,
    position_canonical: Optional[str] = None,
) -> Set[str]:
    """Collect the union of position tokens from all position fields of a defect.

    When soft canonicalization is in effect a found defect may carry three
    related position strings.  For candidate-filtering we need the union so
    that a match can succeed on *either* the reviewer-provided position *or*
    the inferred canonical section.

    Args:
        position: Primary position string (kept as reviewer-original after soft canon).
        original_position: Pre-inference position (may duplicate *position*).
        position_canonical: Inferred/canonical position (e.g. section from evidence).

    Returns:
        Set of unique position tokens extracted from all three fields.
    """
    tokens: Set[str] = set(extract_position_tokens(position))
    if original_position:
        tokens |= set(extract_position_tokens(original_position))
    if position_canonical:
        tokens |= set(extract_position_tokens(position_canonical))
    return tokens


def has_valid_position_tokens(text: str) -> bool:
    """Check if position text contains at least one valid token.

    Args:
        text: Position text to check

    Returns:
        True if at least one valid section or table token is found.
    """
    return bool(extract_position_tokens(text))


def is_use_case_only_position(text: str) -> bool:
    """Check if position refers only to use cases (no valid section/table tokens).

    Args:
        text: Position text to check

    Returns:
        True if position mentions "use case" and has no valid section/table tokens.
    """
    text_lower = text.lower()
    has_use_case = "use case" in text_lower or "usecase" in text_lower
    has_valid_tokens = has_valid_position_tokens(text)

    return has_use_case and not has_valid_tokens


# ---------------------------------------------------------------------------
# Signal token extraction
# ---------------------------------------------------------------------------

# Underscore-separated signal names: Reject_Order, Start_Voice, allocate_car
_UNDERSCORE_SIGNAL = re.compile(r'\b([A-Za-z][a-z]*(?:_[A-Za-z][a-z]*)+)\b')

# CamelCase signal names (2+ words): OrderOper, LoginOk
_CAMELCASE_SIGNAL = re.compile(r'\b([A-Z][a-z]+(?:[A-Z][a-z]*)+)\b')


def _normalize_signal(name: str) -> str:
    """Normalize a signal name for comparison.

    Converts to lowercase and replaces spaces with underscores.

    Args:
        name: Raw signal name

    Returns:
        Normalized signal token
    """
    return name.strip().lower().replace(" ", "_")


def extract_signal_tokens(text: str) -> Set[str]:
    """Extract signal/entity tokens from description text.

    Extracts signal names from:
    - Single-quoted strings: 'Reject_Order', 'Logged In'
    - Double-quoted strings: "start alarm"
    - Underscore-separated names: Reject_Order, Start_Voice
    - CamelCase names: OrderOper, LoginOk

    All tokens are normalized to lowercase with spaces replaced by underscores.

    Args:
        text: Description or evidence text

    Returns:
        Set of normalized signal tokens.

    Examples:
        >>> sorted(extract_signal_tokens("The signal 'Reject_Order' is missing"))
        ['reject_order']
        >>> sorted(extract_signal_tokens("Signal OrderOper should include ack"))
        ['order_oper', 'orderoper']
        >>> sorted(extract_signal_tokens("The signal 'Logged In' misses params"))
        ['logged_in']
    """
    if not text:
        return set()

    tokens: Set[str] = set()

    # 0. Topic prefix extraction: text before first period, if 2-4 words and <= 40 chars
    _TOPIC_SKIP_WORDS = {
        "the", "a", "an", "this", "that", "there", "it", "no", "if",
        "when", "for", "in", "on", "missing", "incorrect", "wrong",
        "parameter", "parameters", "signal", "table", "section",
        # Safety: domain-generic words that are not signal names
        "msc", "design", "page", "note", "see", "requirement",
        "diagram", "specification", "document", "correct",
    }
    dot_pos = text.find(".")
    if dot_pos > 0:
        prefix = text[:dot_pos].strip()
        words = prefix.split()
        if (
            1 <= len(words) <= 4
            and len(prefix) <= 40
            and words[0][0].isupper()
            and words[0].lower() not in _TOPIC_SKIP_WORDS
        ):
            # Single-word prefixes require minimum 3 characters
            if len(words) > 1 or len(words[0]) >= 3:
                tokens.add(_normalize_signal(prefix))

    # 1. Single-quoted names (highest priority - explicit signal references)
    for match in re.finditer(r"'([^']{2,})'", text):
        tokens.add(_normalize_signal(match.group(1)))

    # 2. Double-quoted names
    for match in re.finditer(r'"([^"]{2,})"', text):
        tokens.add(_normalize_signal(match.group(1)))

    # 3. Underscore-separated names (very distinctive)
    for match in _UNDERSCORE_SIGNAL.finditer(text):
        tokens.add(_normalize_signal(match.group(1)))

    # 4. CamelCase names (2+ words)
    for match in _CAMELCASE_SIGNAL.finditer(text):
        raw = match.group(1)
        # Add both forms: joined lowercase and split-on-caps with underscores
        tokens.add(raw.lower())
        # Split CamelCase: OrderOper -> order_oper
        split = re.sub(r'([a-z])([A-Z])', r'\1_\2', raw).lower()
        if split != raw.lower():
            tokens.add(split)

    return tokens


def build_allowed_position_tokens(artifact_text: str) -> Set[str]:
    """Build the set of position tokens that actually appear in the artifact text.

    Use this to reject hallucinated positions (e.g. "3.5" when only 3.1-3.4 exist).

    Args:
        artifact_text: Full text extracted from the inspection artifact (all pages).

    Returns:
        Set of canonical position tokens found in the artifact text.
        Empty set if no valid tokens found.

    Examples:
        >>> sorted(build_allowed_position_tokens("3.1 Data Structures\\n3.2 Signals"))
        ['3.1', '3.2']
    """
    if not artifact_text:
        return set()
    return set(extract_position_tokens(artifact_text))


@dataclass
class PositionCanonResult:
    """Result of defect position canonicalization and drift detection."""

    canonical: str
    original: str
    mentions: List[str] = field(default_factory=list)
    autofixed: bool = False
    autofix_reason: str = ""
    drift_detected: bool = False


def canonicalize_defect_position(
    position: str,
    description: str,
    evidence_text: str,
    allowed_tokens: Optional[Set[str]] = None,
) -> PositionCanonResult:
    """Canonicalize a defect position and detect/autofix position drift.

    Position drift occurs when the position field doesn't match the sections
    actually referenced in the description and evidence text.

    Safety constraints for autofix:
    - Only autofix when exactly ONE mentioned token exists in the valid set.
    - Never autofix when multiple conflicting mentions exist.
    - For Table tokens, only autofix when explicitly mentioned in text.

    Args:
        position: Raw position string from reviewer
        description: Defect description text
        evidence_text: Evidence text (plain string)
        allowed_tokens: Set of valid position tokens from artifact.
            If None, only basic canonicalization is performed.

    Returns:
        PositionCanonResult with canonical position, mentions, and drift info.
    """
    original = position
    pos_tokens = set(extract_position_tokens(position))
    canonical = canonicalize_position(position) or position

    # Extract mentions from description and evidence
    desc_tokens = extract_position_tokens(description)
    ev_tokens = extract_position_tokens(evidence_text)
    all_mention_tokens = sorted(set(desc_tokens + ev_tokens))
    mention_set = set(all_mention_tokens)

    # Without allowed tokens, we can only do basic canonicalization
    if not allowed_tokens:
        return PositionCanonResult(
            canonical=canonical, original=original,
            mentions=all_mention_tokens,
        )

    # Detect hallucinated position tokens
    hallucinated = pos_tokens - allowed_tokens if pos_tokens else set()

    # Detect position/mention mismatch (position tokens valid but don't match text)
    position_mention_mismatch = (
        bool(mention_set) and bool(pos_tokens) and not (pos_tokens & mention_set)
    )

    drift_detected = bool(hallucinated) or position_mention_mismatch

    if not drift_detected:
        return PositionCanonResult(
            canonical=canonical, original=original,
            mentions=all_mention_tokens,
        )

    # Drift detected — attempt safe autofix
    valid_mentions = sorted(mention_set & allowed_tokens)
    if len(valid_mentions) == 1:
        return PositionCanonResult(
            canonical=valid_mentions[0], original=original,
            mentions=all_mention_tokens,
            autofixed=True,
            autofix_reason="single_mentioned_token",
            drift_detected=True,
        )

    # Multiple or no valid mentions — cannot safely autofix
    return PositionCanonResult(
        canonical=canonical, original=original,
        mentions=all_mention_tokens,
        drift_detected=True,
    )


def infer_position_from_context(
    position: str, description: str, evidence_text: str, allowed_tokens: Set[str]
) -> Tuple[str, Optional[str]]:
    """Try to infer a valid position from context when position tokens are hallucinated.

    Args:
        position: Original position string
        description: Defect description text
        evidence_text: Defect evidence text (plain string)
        allowed_tokens: Set of valid position tokens from artifact

    Returns:
        Tuple of (position, original_position).
        If no inference needed or possible, original_position is None.
    """
    # 1. Check if current position tokens are all valid
    pos_tokens = set(extract_position_tokens(position))
    if pos_tokens and pos_tokens <= allowed_tokens:
        return position, None  # Already valid

    # 2. Try to infer from evidence text
    evidence_tokens = set(extract_position_tokens(evidence_text))
    valid_evidence = evidence_tokens & allowed_tokens
    if valid_evidence:
        inferred = canonicalize_position(", ".join(sorted(valid_evidence)))
        return inferred, position

    # 3. Try to infer from description text
    desc_tokens = set(extract_position_tokens(description))
    valid_desc = desc_tokens & allowed_tokens
    if valid_desc:
        inferred = canonicalize_position(", ".join(sorted(valid_desc)))
        return inferred, position

    # 4. No inference possible
    return position, None


def shares_signal_token(text_a: str, text_b: str) -> bool:
    """Check if two texts share at least one signal token.

    Args:
        text_a: First description text
        text_b: Second description text

    Returns:
        True if at least one signal token appears in both texts.

    Examples:
        >>> shares_signal_token("signal 'Reject_Order'", "signal 'Reject_Order' missing")
        True
        >>> shares_signal_token("signal 'Reject_Order'", "signal 'Start_Voice'")
        False
        >>> shares_signal_token("signal 'Order'", "signal 'Logged In'")
        False
    """
    tokens_a = extract_signal_tokens(text_a)
    tokens_b = extract_signal_tokens(text_b)

    if not tokens_a or not tokens_b:
        return False

    return bool(tokens_a & tokens_b)


# ---------------------------------------------------------------------------
# Domain token extraction
# ---------------------------------------------------------------------------


def extract_domain_tokens(signal_tokens: Set[str]) -> Set[str]:
    """Split signal tokens at underscores to get domain sub-tokens.

    Useful for approximate signal matching when exact signal names differ
    but share domain concepts (e.g., 'order_reject' and 'reject_order'
    both yield 'order' and 'reject').

    Only tokens with length >= 3 are included to avoid noise.

    Args:
        signal_tokens: Set of normalized signal tokens.

    Returns:
        Set of domain sub-tokens.

    Examples:
        >>> sorted(extract_domain_tokens({'order_reject'}))
        ['order', 'reject']
        >>> sorted(extract_domain_tokens({'confirm_voice'}))
        ['confirm', 'voice']
        >>> sorted(extract_domain_tokens({'bill'}))
        ['bill']
    """
    domain: Set[str] = set()
    for token in signal_tokens:
        parts = token.split("_")
        for part in parts:
            if len(part) >= 3:
                domain.add(part)
    return domain


# ---------------------------------------------------------------------------
# Description normalization and feature extraction
# ---------------------------------------------------------------------------

_DESC_STOPWORDS = frozenset({
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "in", "on", "at", "to", "for", "of", "with", "by", "from",
    "and", "or", "not", "but", "this", "that", "it", "its",
    "has", "have", "had", "does", "do", "did", "should", "must",
    "can", "will", "would", "could", "may", "might",
    "no", "nor", "if", "then", "when", "where", "which", "what",
    "there", "here", "also", "as", "so", "than", "each", "all",
    "any", "some", "such", "only", "very",
})


def normalize_desc(text: str) -> List[str]:
    """Normalize description text to core content tokens.

    Processing:
    - Lowercases text
    - Removes punctuation (preserves underscores)
    - Splits into tokens
    - Removes English stopwords and tokens shorter than 2 characters
    - Returns deduplicated tokens in order of first appearance

    Deterministic and reproducible.

    Args:
        text: Description text to normalize.

    Returns:
        List of content tokens (deduplicated, order-preserving).

    Examples:
        >>> normalize_desc("The signal 'Order' is missing from the design.")
        ['signal', 'order', 'missing', 'design']
        >>> normalize_desc("")
        []
    """
    if not text:
        return []
    text = text.lower()
    # Replace punctuation with spaces, keep underscores
    text = re.sub(r"[^\w\s]", " ", text)
    words = text.split()
    seen: Set[str] = set()
    result: List[str] = []
    for w in words:
        if w not in _DESC_STOPWORDS and len(w) >= 2 and w not in seen:
            seen.add(w)
            result.append(w)
    return result


_FEATURE_KEYWORDS = frozenset({
    "missing", "ack", "timeout", "parameter", "undefined",
    "inconsistent", "wrong", "incorrect", "alarm", "signal",
})

_FEATURE_SYNONYMS = {
    "acknowledgment": "ack",
    "acknowledgement": "ack",
    "parameters": "parameter",
}


def feature_flags(tokens: List[str]) -> Set[str]:
    """Extract defect-category feature flags from normalized tokens.

    Normalizes synonyms (e.g., 'acknowledgment' -> 'ack') and returns
    the intersection with known feature keywords.

    Args:
        tokens: Normalized description tokens (from normalize_desc()).

    Returns:
        Set of canonical feature keywords found in tokens.

    Examples:
        >>> sorted(feature_flags(['missing', 'acknowledgment', 'signal']))
        ['ack', 'missing', 'signal']
        >>> sorted(feature_flags(['timeout', 'specified']))
        ['timeout']
    """
    flags: Set[str] = set()
    for t in tokens:
        canonical = _FEATURE_SYNONYMS.get(t, t)
        if canonical in _FEATURE_KEYWORDS:
            flags.add(canonical)
    return flags
