"""Defect matching between found and gold standard."""

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from rapidfuzz import fuzz

from ..core.schemas import Defect, DefectMatch, GoldDefect, MatchType
from ..utils.position_tokens import (
    collect_defect_position_tokens,
    extract_domain_tokens,
    extract_position_tokens,
    extract_signal_tokens,
    feature_flags,
    normalize_desc,
    shares_position_token,
)


@dataclass
class SimilarityResult:
    """Result of similarity calculation with diagnostic reason."""

    score: float
    reason: str


class DefectMatcher:
    """Match found defects against gold standard."""

    def __init__(
        self,
        position_threshold: float = 0.7,
        description_threshold: float = 0.6,
        exact_threshold: float = 0.85,
    ):
        """Initialize matcher.

        Args:
            position_threshold: Minimum similarity for position match
            description_threshold: Minimum similarity for description match
            exact_threshold: Minimum similarity for exact match
        """
        self.position_threshold = position_threshold
        self.description_threshold = description_threshold
        self.exact_threshold = exact_threshold

    def match(
        self,
        found_defects: List[Defect],
        gold_defects: List[GoldDefect],
        debug_output_dir: Optional[Path] = None,
    ) -> Tuple[List[DefectMatch], Dict]:
        """Match found defects against gold standard.

        Args:
            found_defects: List of found defects
            gold_defects: List of gold standard defects
            debug_output_dir: Optional directory to write match_debug.jsonl
                (also enabled by env var FAGAN_MATCH_DEBUG=1)

        Returns:
            Tuple of (matches list, stats dict)
        """
        # Match debug: collect candidate-pair records
        debug_enabled = os.environ.get("FAGAN_MATCH_DEBUG", "0") == "1" or debug_output_dir is not None
        debug_records: List[dict] = []

        matches = []
        matched_gold_ids: Set[str] = set()
        matched_found_ids: Set[str] = set()

        # Track best candidate for every found defect (across ALL gold, even matched)
        best_candidate_info: Dict[str, dict] = {}

        # First pass: exact and partial matches
        for found in found_defects:
            best_match = None
            best_score = 0.0
            best_gold = None

            # Track absolute best candidate across ALL gold (for debug)
            abs_best_score = 0.0
            abs_best_gold = None
            abs_best_reason = "no_candidates"

            for gold in gold_defects:
                result = self._calculate_similarity(found, gold)

                # Collect debug record for this candidate pair
                if debug_enabled:
                    found_tokens = sorted(collect_defect_position_tokens(
                        found.position,
                        getattr(found, "original_position", None),
                        getattr(found, "position_canonical", None),
                    ))
                    gold_tokens = sorted(set(extract_position_tokens(gold.position)))
                    pos_overlap_set = set(found_tokens) & set(gold_tokens)
                    # Signal extraction for debug
                    dbg_found_signals = extract_signal_tokens(found.description)
                    dbg_ev_text = self._get_evidence_text(found.evidence)
                    if dbg_ev_text:
                        dbg_found_signals |= extract_signal_tokens(dbg_ev_text)
                    dbg_gold_signals = extract_signal_tokens(gold.description)
                    dbg_found_norm = normalize_desc(found.description)
                    dbg_gold_norm = normalize_desc(gold.description)
                    debug_records.append({
                        "found_id": found.id,
                        "found_position": found.position,
                        "found_tokens": found_tokens,
                        "gold_id": gold.id,
                        "gold_position": gold.position,
                        "gold_tokens": gold_tokens,
                        "position_overlap_count": len(pos_overlap_set),
                        "signal_overlap_count": len(dbg_found_signals & dbg_gold_signals),
                        "extracted_signals_found": sorted(dbg_found_signals),
                        "extracted_signals_gold": sorted(dbg_gold_signals),
                        "normalized_desc_tokens_found": len(dbg_found_norm),
                        "normalized_desc_tokens_gold": len(dbg_gold_norm),
                        "feature_flags_found": sorted(feature_flags(dbg_found_norm)),
                        "feature_flags_gold": sorted(feature_flags(dbg_gold_norm)),
                        "combined_score": result.score,
                        "reason": result.reason,
                    })

                # Track absolute best for debug (regardless of matched status)
                if result.score > abs_best_score or (
                    result.score == 0.0
                    and abs_best_score == 0.0
                    and self._reason_priority(result.reason) > self._reason_priority(abs_best_reason)
                ):
                    if result.score > abs_best_score:
                        abs_best_score = result.score
                    abs_best_gold = gold
                    abs_best_reason = result.reason

                # Only consider unmatched gold for actual matching
                if gold.id in matched_gold_ids:
                    continue

                if result.score > best_score:
                    best_score = result.score
                    best_gold = gold
                    best_match = self._determine_match_type(result.score, found, gold)

            # Store best candidate info for this found defect
            if abs_best_gold is not None:
                # If best candidate matched but below threshold, refine reason
                effective_reason = abs_best_reason
                if abs_best_reason == "matched" and abs_best_score < self.description_threshold:
                    effective_reason = "below_threshold"
                best_candidate_info[found.id] = {
                    "gold_id": abs_best_gold.id,
                    "gold_position": abs_best_gold.position,
                    "similarity": abs_best_score,
                    "reason": effective_reason,
                }

            if best_match and best_score >= self.description_threshold:
                match = DefectMatch(
                    found_id=found.id,
                    gold_id=best_gold.id,
                    match_type=best_match,
                    similarity_score=best_score,
                    notes=f"Matched with {best_score:.2f} similarity",
                )
                matches.append(match)
                matched_gold_ids.add(best_gold.id)
                matched_found_ids.add(found.id)

        # Second pass: identify duplicates (found defects matching same gold)
        duplicate_groups = self._find_duplicates(found_defects, matches)
        for dup_found_id in duplicate_groups:
            if dup_found_id not in matched_found_ids:
                match = DefectMatch(
                    found_id=dup_found_id,
                    gold_id=None,
                    match_type=MatchType.DUPLICATE,
                    similarity_score=0.0,
                    notes="Duplicate of another found defect",
                )
                matches.append(match)
                matched_found_ids.add(dup_found_id)

        # Third pass: unmatched found defects (potential new or false positives)
        for found in found_defects:
            if found.id not in matched_found_ids:
                # Determine if defect is in-scope or out-of-scope
                is_out_of_scope = self._is_out_of_scope(found)

                # Check confidence to distinguish potential new vs false positive
                if found.confidence >= 0.7:
                    match_type = MatchType.NO_MATCH_POTENTIAL_NEW
                    scope_note = " (out-of-scope: use case)" if is_out_of_scope else " (in-scope)"
                    notes = f"Potential new defect (high confidence, not in gold){scope_note}"
                else:
                    match_type = MatchType.NO_MATCH_FALSE_POSITIVE
                    scope_note = " (out-of-scope: use case)" if is_out_of_scope else " (in-scope)"
                    notes = f"Likely false positive (low confidence, not in gold){scope_note}"

                match = DefectMatch(
                    found_id=found.id,
                    gold_id=None,
                    match_type=match_type,
                    similarity_score=0.0,
                    notes=notes,
                )
                matches.append(match)

        # Populate debug fields on ALL match objects
        for match in matches:
            info = best_candidate_info.get(match.found_id)
            if info:
                match.best_candidate_gold_id = info["gold_id"]
                match.best_candidate_gold_position = info["gold_position"]
                match.best_candidate_similarity = info["similarity"]
                match.best_candidate_match_reason = (
                    "matched" if match.gold_id is not None else info["reason"]
                )

        # Calculate stats
        stats = {
            "total_found": len(found_defects),
            "total_gold": len(gold_defects),
            "matched": len(matched_gold_ids),
            "duplicates": len(duplicate_groups),
            "false_positives": sum(
                1 for m in matches if m.match_type == MatchType.NO_MATCH_FALSE_POSITIVE
            ),
            "potential_new": sum(
                1 for m in matches if m.match_type == MatchType.NO_MATCH_POTENTIAL_NEW
            ),
            "false_negatives": len(gold_defects) - len(matched_gold_ids),
        }

        # Write match debug file if enabled
        if debug_enabled and debug_records:
            self._write_debug(debug_records, debug_output_dir)

        return matches, stats

    def _write_debug(
        self,
        records: List[dict],
        output_dir: Optional[Path] = None,
    ) -> None:
        """Write match debug records to JSONL file.

        Writes up to 50 records sorted by combined_score descending
        (non-zero scores first, then by reason priority).

        Args:
            records: Debug records collected during matching
            output_dir: Directory for output; defaults to current directory
        """
        # Sort: non-zero scores first (descending), then by reason priority
        def sort_key(r: dict) -> tuple:
            return (-r["combined_score"], -self._reason_priority(r["reason"]))

        records.sort(key=sort_key)
        top_records = records[:50]

        out_dir = output_dir or Path(".")
        out_dir.mkdir(parents=True, exist_ok=True)
        debug_path = out_dir / "match_debug.jsonl"

        with open(debug_path, "w") as f:
            for rec in top_records:
                f.write(json.dumps(rec, default=str) + "\n")

        print(f"[MATCH_DEBUG] Wrote {len(top_records)} records to {debug_path}")

    def _calculate_similarity(self, found: Defect, gold: GoldDefect) -> SimilarityResult:
        """Calculate similarity between found and gold defect.

        Gates (return 0.0 if any fail):
        1. Positions must share at least one token (union matching).
        2. Signal tokens: if both sides carry signals, they must share at
           least one exact signal OR >= 2 domain sub-tokens.
        3. If NEITHER side has signal tokens, description similarity must
           be >= 0.80.
        A3: If gold has >= 3 same-granularity positions and overlap < 2
            (without signal confirmation), reject.

        Position scoring uses the Overlap Coefficient:
            |A ∩ B| / min(|A|, |B|)

        Description similarity blends rapidfuzz token_sort_ratio (primary)
        with a feature-based adjustment (A2).

        Args:
            found: Found defect
            gold: Gold defect

        Returns:
            SimilarityResult with score (0.0 to 1.0) and diagnostic reason
        """
        # GATE 1: Check for shared position token (union matching).
        found_pos_tokens = collect_defect_position_tokens(
            found.position,
            getattr(found, "original_position", None),
            getattr(found, "position_canonical", None),
        )
        gold_pos_tokens = set(extract_position_tokens(gold.position))
        if not found_pos_tokens or not gold_pos_tokens:
            return SimilarityResult(0.0, "no_position_overlap")

        pos_overlap = found_pos_tokens & gold_pos_tokens
        if not pos_overlap:
            return SimilarityResult(0.0, "no_position_overlap")

        # --- Signal extraction (needed for A3 and Gate 2) ---
        found_signals = extract_signal_tokens(found.description)
        found_evidence_text = self._get_evidence_text(found.evidence)
        if found_evidence_text:
            found_signals |= extract_signal_tokens(found_evidence_text)

        gold_signals = extract_signal_tokens(gold.description)

        found_domain = extract_domain_tokens(found_signals)
        gold_domain = extract_domain_tokens(gold_signals)

        both_have_signals = bool(found_signals) and bool(gold_signals)
        neither_has_signals = not found_signals and not gold_signals
        signal_exact_overlap = found_signals & gold_signals if both_have_signals else set()
        domain_overlap = found_domain & gold_domain
        has_signal_confirmation = bool(signal_exact_overlap) or len(domain_overlap) >= 2

        # --- A3: Conservative multi-position filter ---
        # When gold references many positions and found overlaps weakly,
        # reject unless signals confirm the match.
        if len(gold_pos_tokens) >= 2 and len(pos_overlap) < 2 and not has_signal_confirmation:
            max_spec = max(self._token_specificity(t) for t in gold_pos_tokens)
            most_specific = {t for t in gold_pos_tokens if self._token_specificity(t) == max_spec}
            # Single unique most-specific token: matching it is sufficient
            if len(most_specific) == 1 and (pos_overlap & most_specific):
                pass  # OK: matched the most specific token
            elif len(gold_pos_tokens) >= 3:
                # Many same-granularity positions, weak overlap → reject
                return SimilarityResult(0.0, "insufficient_position_overlap")

        # --- GATE 2: Signal token constraint (A1 enhanced) ---
        if both_have_signals:
            if not signal_exact_overlap and len(domain_overlap) < 2:
                return SimilarityResult(0.0, "no_signal_overlap")

        # One side has signals: check domain overlap in other's description
        score_dampening = 1.0
        one_side_signals = not both_have_signals and not neither_has_signals
        if one_side_signals:
            if found_signals and not gold_signals:
                other_desc_tokens = set(normalize_desc(gold.description))
                has_domain_in_desc = bool(found_domain & other_desc_tokens)
            else:
                other_desc_tokens = set(normalize_desc(found.description))
                has_domain_in_desc = bool(gold_domain & other_desc_tokens)
            if not has_domain_in_desc:
                score_dampening = 0.75  # Dampen by 25%

        # --- Description similarity ---
        found_desc = self._normalize_text(found.description)
        gold_desc = self._normalize_text(gold.description)
        desc_sim = fuzz.token_sort_ratio(found_desc, gold_desc) / 100.0

        # GATE 3: When NEITHER side has signal tokens, require high
        # description similarity to avoid spurious matches on position alone.
        if neither_has_signals:
            if desc_sim < 0.80:
                return SimilarityResult(0.0, "low_desc_sim_no_signals")

        # --- A2: Feature-based adjustment ---
        found_norm = normalize_desc(found.description)
        gold_norm = normalize_desc(gold.description)
        feature_bonus = 0.0
        if found_norm and gold_norm:
            found_features = feature_flags(found_norm)
            gold_features = feature_flags(gold_norm)
            # Only apply bonus/penalty when both sides have feature keywords
            if found_features and gold_features:
                f_overlap = found_features & gold_features
                f_diff = found_features.symmetric_difference(gold_features)
                feature_bonus = len(f_overlap) * 0.02 - len(f_diff) * 0.015
                feature_bonus = max(-0.05, min(0.05, feature_bonus))

        # --- Position score: Overlap Coefficient ---
        pos_sim = len(pos_overlap) / min(len(found_pos_tokens), len(gold_pos_tokens))

        # Risk and type match bonus
        risk_match = 0.05 if found.risk == gold.risk else 0.0
        type_match = 0.05 if found.fault_type == gold.fault_type else 0.0

        # Weighted score: position (30%) + description (60%) + attributes (10%)
        score = (pos_sim * 0.3) + (desc_sim * 0.6) + risk_match + type_match
        score += feature_bonus
        score *= score_dampening
        score = max(0.0, min(1.0, score))

        return SimilarityResult(score, "matched")

    def _determine_match_type(self, score: float, found: Defect, gold: GoldDefect) -> MatchType:
        """Determine match type based on score and attributes.

        Args:
            score: Similarity score
            found: Found defect
            gold: Gold defect

        Returns:
            MatchType
        """
        if score >= self.exact_threshold:
            return MatchType.EXACT
        else:
            return MatchType.PARTIAL

    def _find_duplicates(
        self,
        found_defects: List[Defect],
        existing_matches: List[DefectMatch],
    ) -> Set[str]:
        """Find duplicate defects in found list.

        Args:
            found_defects: List of found defects
            existing_matches: Already established matches

        Returns:
            Set of duplicate found IDs
        """
        duplicates = set()
        processed = set()

        for i, found1 in enumerate(found_defects):
            if found1.id in processed:
                continue

            for found2 in found_defects[i + 1 :]:
                if found2.id in processed:
                    continue

                # Calculate similarity between two found defects
                sim = self._calculate_found_similarity(found1, found2)

                if sim >= 0.8:  # High similarity indicates duplicate
                    # Mark the one with lower confidence as duplicate
                    if found1.confidence >= found2.confidence:
                        duplicates.add(found2.id)
                        processed.add(found2.id)
                    else:
                        duplicates.add(found1.id)
                        processed.add(found1.id)
                        break

        return duplicates

    def _calculate_found_similarity(self, found1: Defect, found2: Defect) -> float:
        """Calculate similarity between two found defects.

        IMPORTANT: Returns 0.0 if positions don't share at least one token.
        This prevents over-aggressive duplicate detection.

        Args:
            found1: First defect
            found2: Second defect

        Returns:
            Similarity score, or 0.0 if no shared position token
        """
        # CRITICAL: Check for shared position token FIRST
        # Different positions cannot be duplicates
        tokens1 = set(extract_position_tokens(found1.position))
        tokens2 = set(extract_position_tokens(found2.position))
        if not tokens1 or not tokens2 or not (tokens1 & tokens2):
            return 0.0

        desc1 = self._normalize_text(found1.description)
        desc2 = self._normalize_text(found2.description)

        # Position score: Overlap Coefficient
        intersection = tokens1 & tokens2
        pos_sim = len(intersection) / min(len(tokens1), len(tokens2))

        desc_sim = fuzz.token_sort_ratio(desc1, desc2) / 100.0

        return (pos_sim * 0.4) + (desc_sim * 0.6)

    @staticmethod
    def _get_evidence_text(evidence) -> str:
        """Extract plain text from evidence field.

        Args:
            evidence: Evidence value (str or dict)

        Returns:
            Plain text string for signal token extraction.
        """
        if isinstance(evidence, str):
            return evidence
        if isinstance(evidence, dict):
            parts = [v for v in evidence.values() if isinstance(v, str)]
            return " ".join(parts)
        return ""

    def _normalize_position(self, position: str) -> str:
        """Normalize position string.

        Args:
            position: Position string

        Returns:
            Normalized position
        """
        return position.lower().strip().replace("section", "").replace("page", "").strip()

    def _normalize_text(self, text: str) -> str:
        """Normalize text for comparison.

        Args:
            text: Text to normalize

        Returns:
            Normalized text
        """
        return text.lower().strip()

    def _is_out_of_scope(self, defect: Defect) -> bool:
        """Determine if a defect is out-of-scope (use case position).

        Gold standard only contains Design/MSC defects. Defects with
        "use case" in position are out of scope by definition.

        Args:
            defect: Defect to check

        Returns:
            True if out-of-scope (use case), False if in-scope
        """
        position_lower = defect.position.lower()
        return "use case" in position_lower or "usecase" in position_lower

    @staticmethod
    def _token_specificity(token: str) -> int:
        """Return specificity level of a position token.

        Higher = more specific/granular.
        - "3.4.2" (3 levels) → 3
        - "3.4"   (2 levels) → 2
        - "Table 1"          → 2 (moderately specific)

        Args:
            token: Position token string.

        Returns:
            Integer specificity level.
        """
        if token.startswith("Table"):
            return 2
        return len(token.split("."))

    @staticmethod
    def _reason_priority(reason: str) -> int:
        """Return priority rank for similarity reasons (higher = more informative).

        Used to pick the most informative reason when multiple candidates
        have the same score of 0.0.
        """
        priority = {
            "no_candidates": 0,
            "no_position_overlap": 1,
            "insufficient_position_overlap": 2,
            "no_signal_overlap": 3,
            "low_desc_sim_no_signals": 4,
            "below_threshold": 5,
            "matched": 6,
        }
        return priority.get(reason, 0)
