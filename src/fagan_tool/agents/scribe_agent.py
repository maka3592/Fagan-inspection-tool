"""Scribe agent for inspection meeting consolidation."""

import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from rapidfuzz import fuzz

from ..core.schemas import (
    ConflictRecord,
    Defect,
    DuplicateGroup,
    FaultType,
    IncompleteDefect,
    MeetingOutput,
    ReviewerOutput,
    RiskLevel,
)
from ..providers.openai_provider import SCRIBE_OUTPUT_SCHEMA
from ..utils.position_tokens import (
    PositionCanonResult,
    canonicalize_defect_position,
    canonicalize_position,
    extract_position_tokens,
    extract_signal_tokens,
    has_valid_position_tokens,
    is_use_case_only_position,
    shares_position_token,
    shares_signal_token,
)
from .base_agent import BaseAgent

# Minimum description similarity for two defects to be considered the same
DEDUP_SIMILARITY_THRESHOLD = 0.85

# Minimum description similarity for mapping a consolidated defect to its source
PROVENANCE_MAPPING_THRESHOLD = 0.50

# JSON response format for OpenAI API - use strict JSON Schema for reliability
JSON_RESPONSE_FORMAT = {
    "type": "json_schema",
    "json_schema": SCRIBE_OUTPUT_SCHEMA
}


class ScribeAgent(BaseAgent):
    """Agent that consolidates findings in inspection meeting."""

    def __init__(self, provider, prompt_dir, debug_dir: Optional[Path] = None):
        """Initialize scribe agent.

        Args:
            provider: LLM provider instance
            prompt_dir: Directory containing prompt templates
            debug_dir: Optional directory for debug output
        """
        super().__init__(provider, "scribe", prompt_dir, debug_dir=debug_dir)

    def consolidate(
        self,
        reviewer_outputs: List[ReviewerOutput],
        allowed_position_tokens: Optional[set] = None,
    ) -> MeetingOutput:
        """Consolidate reviewer findings into final defect list.

        Args:
            reviewer_outputs: Outputs from all reviewers

        Returns:
            MeetingOutput with consolidated defects and meeting minutes
        """
        # Load prompt
        template = self.load_prompt("scribe_meeting.txt")

        # Prepare reviewer findings
        reviewer_context = self._format_reviewer_outputs(reviewer_outputs)

        system_prompt = template

        user_message = f"""
Consolidate the following reviewer findings from the inspection meeting.

{reviewer_context}

Tasks:
1. Merge duplicate defects (same position, similar description)
2. Resolve conflicts (different risk/fault_type for same defect)
3. Flag uncertain items that need clarification
4. Create consolidated defect list
5. Write meeting minutes summary
6. Make exit decision (Accept / Conditional Accept / Reject)

Return ONLY valid JSON, no explanations or markdown:
{{
  "consolidated_defects": [
    {{
      "position": "...",
      "page_hint": "...",
      "risk": "A/B/C/UNK",
      "fault_type": "M/W/UNK",
      "description": "...",
      "evidence": "...",
      "confidence": 0.8,
      "flags": []
    }}
  ],
  "duplicates_removed": 5,
  "conflicts_flagged": 2,
  "minutes": "Meeting summary text...",
  "exit_decision": "Conditional Accept - 15 defects found, rework required"
}}
"""

        # Use JSON response format for structured output
        response = self.call_llm(
            user_message, system_prompt, response_format=JSON_RESPONSE_FORMAT
        )

        # Parse response
        try:
            data = self.extract_json_from_response(response, context="scribe_meeting")

            consolidated_defects = []
            incomplete_defects = []

            for d in data.get("consolidated_defects", []):
                # Validate mandatory fields before creating defect
                validation_result = self._validate_defect_completeness(
                    d, allowed_position_tokens=allowed_position_tokens
                )

                if validation_result["is_complete"]:
                    # Always use the (possibly-original) position for the primary
                    # field so it keeps section alignment with the gold standard.
                    # The inferred canonical goes into position_canonical only.
                    raw_position = d.get("position", "unknown")
                    canonical_pos = canonicalize_position(raw_position)
                    final_position = canonical_pos if canonical_pos else raw_position

                    defect = Defect(
                        id=f"meeting_{uuid.uuid4().hex[:8]}",
                        position=final_position,
                        page_hint=d.get("page_hint"),
                        risk=RiskLevel(d.get("risk", "UNK")),
                        fault_type=FaultType(d.get("fault_type", "UNK")),
                        description=d.get("description", ""),
                        evidence=d.get("evidence", ""),
                        confidence=float(d.get("confidence", 0.8)),
                        flags=d.get("flags", []),
                        original_position=d.get("_original_position"),
                        # Position canonicalization fields
                        position_canonical=d.get("_canon_canonical", final_position),
                        position_mentions=d.get("_canon_mentions", []),
                        position_autofixed=d.get("_canon_autofixed", False),
                        position_autofix_reason=d.get("_canon_autofix_reason", ""),
                    )
                    consolidated_defects.append(defect)
                else:
                    # Store incomplete defect with reason
                    incomplete = IncompleteDefect(
                        original_data=d,
                        reason=validation_result["reason"],
                        reviewer_id=d.get("reviewer_id")
                    )
                    incomplete_defects.append(incomplete)

            # Rescue distinct defects the LLM incorrectly merged
            rescued_defects, rescue_count = self._validate_and_rescue(
                consolidated_defects, reviewer_outputs,
                allowed_position_tokens=allowed_position_tokens,
            )

            # Map provenance: link each consolidated defect to source reviewers
            self._map_provenance(rescued_defects, reviewer_outputs)

            # Build deterministic duplicate groups from provenance data
            duplicate_groups = self._build_duplicate_groups(rescued_defects)
            # Count unique source reviewer defects absorbed as duplicates.
            # merged_ids are source reviewer IDs (canonical is a separate
            # meeting ID), so each group absorbed len(merged_ids) reviewer
            # defects into 1 consolidated defect.  Deduplicate across groups
            # because a single reviewer defect may feed multiple consolidated
            # defects via provenance mapping.
            all_source_ids: set = set()
            for g in duplicate_groups:
                all_source_ids.update(g.merged_ids)
            duplicates_removed = max(0, len(all_source_ids) - len(duplicate_groups))

            # Build structured conflicts
            conflicts = self._detect_conflicts(rescued_defects, reviewer_outputs)

            return MeetingOutput(
                consolidated_defects=rescued_defects,
                incomplete_defects=incomplete_defects,
                duplicates_removed=duplicates_removed,
                conflicts_flagged=len(conflicts),
                duplicate_groups=duplicate_groups,
                conflicts=conflicts,
                minutes=data.get("minutes", ""),
                exit_decision=data.get("exit_decision", "Unknown"),
            )

        except (ValueError, KeyError) as e:
            print(f"Warning: Failed to parse scribe output: {e}")
            # Fallback: just combine all defects
            all_defects = []
            for output in reviewer_outputs:
                all_defects.extend(output.defects)

            return MeetingOutput(
                consolidated_defects=all_defects,
                incomplete_defects=[],
                duplicates_removed=0,
                conflicts_flagged=0,
                minutes=f"Error in consolidation: {str(e)}",
                exit_decision="Error",
            )

    def _validate_defect_completeness(
        self,
        defect_data: Dict[str, Any],
        allowed_position_tokens: Optional[set] = None,
    ) -> Dict[str, Any]:
        """Validate that a defect has all mandatory fields.

        Also validates position tokens - positions must contain valid
        section (3.x, 4.x) or table references. If allowed_position_tokens
        is provided, all position tokens must be present in the allowed set.

        Args:
            defect_data: Raw defect data dictionary
            allowed_position_tokens: Optional set of position tokens from artifact text.
                If provided, defect tokens must be a subset.

        Returns:
            Dict with keys:
                - is_complete (bool): Whether defect is complete
                - reason (str): Explanation if incomplete
                - canonical_position (str): Canonicalized position if valid
        """
        missing_fields = []

        # Check position (must exist and not be "unknown")
        position = defect_data.get("position", "").strip()
        if not position or position.lower() == "unknown":
            missing_fields.append("position (empty or 'unknown')")

        # Validate position tokens - must have valid 3.x/4.x or Table references
        elif not has_valid_position_tokens(position):
            missing_fields.append("position (no valid section/table tokens - must be 3.x, 4.x, or Table N)")

        # Reject use-case-only positions
        elif is_use_case_only_position(position):
            missing_fields.append("position (use case only - needs section/table reference)")

        # Position canonicalization and drift guard
        else:
            evidence = defect_data.get("evidence", "")
            evidence_text = evidence if isinstance(evidence, str) else (
                evidence.get("quote_or_paraphrase", "") if isinstance(evidence, dict) else ""
            )
            description = defect_data.get("description", "")

            canon = canonicalize_defect_position(
                position, description, evidence_text, allowed_position_tokens
            )

            # Store canonicalization results for downstream use
            defect_data["_canon_canonical"] = canon.canonical
            defect_data["_canon_original"] = canon.original
            defect_data["_canon_mentions"] = canon.mentions
            defect_data["_canon_autofixed"] = canon.autofixed
            defect_data["_canon_autofix_reason"] = canon.autofix_reason
            defect_data["_canon_drift_detected"] = canon.drift_detected

            if canon.autofixed:
                # Soft canonicalization: keep original position for gold-matching,
                # store inferred position only in position_canonical.
                # Do NOT overwrite defect_data["position"].
                defect_data["_original_position"] = canon.original
                defect_data.setdefault("flags", [])
                if "position_autofixed" not in defect_data["flags"]:
                    defect_data["flags"].append("position_autofixed")
            elif canon.drift_detected and allowed_position_tokens:
                # Drift detected, autofix failed — reject only if hallucinated
                pos_tokens = set(extract_position_tokens(position))
                hallucinated = pos_tokens - allowed_position_tokens
                if hallucinated:
                    missing_fields.append(
                        f"position (hallucinated tokens not in artifact: {sorted(hallucinated)})"
                    )

        # Check page_hint
        page_hint = defect_data.get("page_hint", "")
        if not page_hint or str(page_hint).strip() == "":
            missing_fields.append("page_hint (empty)")

        # Check description
        description = defect_data.get("description", "").strip()
        if not description:
            missing_fields.append("description (empty)")

        # Check evidence (must be non-empty string or dict with quote_or_paraphrase)
        evidence = defect_data.get("evidence", "")
        if isinstance(evidence, dict):
            quote = evidence.get("quote_or_paraphrase", "").strip()
            if not quote:
                missing_fields.append("evidence.quote_or_paraphrase (empty)")
        elif isinstance(evidence, str):
            if not evidence.strip():
                missing_fields.append("evidence (empty string)")
        else:
            missing_fields.append("evidence (missing or invalid type)")

        # Check risk and fault_type (avoid UNK)
        risk = defect_data.get("risk", "UNK")
        fault_type = defect_data.get("fault_type", "UNK")

        if risk == "UNK":
            missing_fields.append("risk (UNK)")
        if fault_type == "UNK":
            missing_fields.append("fault_type (UNK)")

        if missing_fields:
            return {
                "is_complete": False,
                "reason": f"Missing mandatory fields: {', '.join(missing_fields)}"
            }

        return {
            "is_complete": True,
            "reason": ""
        }

    def _validate_and_rescue(
        self,
        consolidated: List[Defect],
        reviewer_outputs: List[ReviewerOutput],
        allowed_position_tokens: Optional[set] = None,
    ) -> Tuple[List[Defect], int]:
        """Validate consolidation and rescue distinct defects the LLM incorrectly merged.

        Two defects are considered the same ONLY IF both conditions hold:
        1. They share at least one normalized position token
        2. Their descriptions have >= DEDUP_SIMILARITY_THRESHOLD token_sort_ratio

        Any reviewer defect that has no matching consolidated defect is "rescued"
        and added to the final list with a new meeting ID.

        Args:
            consolidated: Defects returned by LLM scribe
            reviewer_outputs: Original reviewer outputs

        Returns:
            Tuple of (final defect list, count of rescued defects)
        """
        # Collect all reviewer defects
        all_reviewer: List[Defect] = []
        for output in reviewer_outputs:
            all_reviewer.extend(output.defects)

        # Build the final list starting from the LLM consolidated output
        final_list = list(consolidated)
        rescued_count = 0

        for defect in all_reviewer:
            desc_lower = defect.description.lower().strip()

            # Check if this reviewer defect is represented in the current final list
            is_represented = False
            for existing in final_list:
                if shares_position_token(defect.position, existing.position):
                    sim = fuzz.token_sort_ratio(
                        desc_lower, existing.description.lower().strip()
                    ) / 100.0
                    if sim >= DEDUP_SIMILARITY_THRESHOLD:
                        is_represented = True
                        break

            if not is_represented:
                # Validate position before rescuing
                raw_position = defect.position

                if not has_valid_position_tokens(raw_position):
                    continue  # Skip defects with invalid positions

                # Canonicalize and check for drift
                evidence = defect.evidence
                evidence_text = evidence if isinstance(evidence, str) else (
                    evidence.get("quote_or_paraphrase", "") if isinstance(evidence, dict) else ""
                )
                canon = canonicalize_defect_position(
                    raw_position, defect.description, evidence_text,
                    allowed_position_tokens,
                )

                # If hallucinated and not autofixed → skip
                if allowed_position_tokens and canon.drift_detected and not canon.autofixed:
                    pos_tokens = set(extract_position_tokens(raw_position))
                    if pos_tokens - allowed_position_tokens:
                        continue

                # Keep original position for gold-matching; canonical goes in
                # position_canonical only (soft canonicalization).
                canonical_pos = canonicalize_position(raw_position)
                final_position = canonical_pos if canonical_pos else raw_position
                flags = list(defect.flags)
                original_pos = None
                if canon.autofixed:
                    original_pos = canon.original
                    if "position_autofixed" not in flags:
                        flags.append("position_autofixed")

                rescued_defect = Defect(
                    id=f"meeting_{uuid.uuid4().hex[:8]}",
                    position=final_position,
                    page_hint=defect.page_hint,
                    risk=defect.risk,
                    fault_type=defect.fault_type,
                    description=defect.description,
                    evidence=defect.evidence,
                    confidence=defect.confidence,
                    flags=flags,
                    reviewer_id=defect.reviewer_id,
                    technique=defect.technique,
                    source_defect_ids=[defect.id],
                    source_reviewer_ids=[defect.reviewer_id] if defect.reviewer_id else [],
                    source_techniques=[defect.technique.value] if defect.technique else [],
                    original_position=original_pos,
                    position_canonical=canon.canonical,
                    position_mentions=canon.mentions,
                    position_autofixed=canon.autofixed,
                    position_autofix_reason=canon.autofix_reason,
                )
                final_list.append(rescued_defect)
                rescued_count += 1

        return final_list, rescued_count

    def _map_provenance(
        self,
        consolidated: List[Defect],
        reviewer_outputs: List[ReviewerOutput],
    ) -> None:
        """Map each consolidated defect to its source reviewer defects.

        Sets source_defect_ids, source_reviewer_ids, source_techniques
        on each consolidated defect in-place. Skips defects that already
        have provenance set (e.g., rescued defects).

        Args:
            consolidated: Consolidated defect list (modified in-place)
            reviewer_outputs: Original reviewer outputs
        """
        all_reviewer: List[Defect] = []
        for output in reviewer_outputs:
            all_reviewer.extend(output.defects)

        for cons_defect in consolidated:
            # Skip if provenance was already set (e.g., rescued defects)
            if cons_defect.source_defect_ids:
                continue

            source_ids = []
            reviewer_ids: set = set()
            techniques: set = set()

            for rev_defect in all_reviewer:
                if not shares_position_token(cons_defect.position, rev_defect.position):
                    continue
                sim = fuzz.token_sort_ratio(
                    cons_defect.description.lower().strip(),
                    rev_defect.description.lower().strip(),
                ) / 100.0
                if sim >= PROVENANCE_MAPPING_THRESHOLD:
                    source_ids.append(rev_defect.id)
                    if rev_defect.reviewer_id:
                        reviewer_ids.add(rev_defect.reviewer_id)
                    if rev_defect.technique:
                        techniques.add(rev_defect.technique.value)

            cons_defect.source_defect_ids = source_ids
            cons_defect.source_reviewer_ids = sorted(reviewer_ids)
            cons_defect.source_techniques = sorted(techniques)

    def _build_duplicate_groups(
        self,
        consolidated: List[Defect],
    ) -> List[DuplicateGroup]:
        """Build deterministic duplicate groups from provenance data.

        A duplicate group exists when a consolidated defect was sourced
        from 2+ distinct reviewer defects.

        Args:
            consolidated: Consolidated defects with provenance mapped

        Returns:
            List of DuplicateGroup records
        """
        groups = []
        for defect in consolidated:
            if len(defect.source_defect_ids) > 1:
                groups.append(DuplicateGroup(
                    canonical_id=defect.id,
                    merged_ids=defect.source_defect_ids,
                    reason="Same position + similar description",
                    position_tokens=extract_position_tokens(defect.position),
                    signal_tokens=sorted(extract_signal_tokens(defect.description)),
                ))
        return groups

    def _detect_conflicts(
        self,
        consolidated: List[Defect],
        reviewer_outputs: List[ReviewerOutput],
    ) -> List[ConflictRecord]:
        """Detect conflicts between source reviewer defects for each consolidated defect.

        A conflict occurs when source reviewer defects that map to the
        same consolidated defect disagree on risk or fault_type.

        Args:
            consolidated: Consolidated defects with provenance mapped
            reviewer_outputs: Original reviewer outputs

        Returns:
            List of ConflictRecord objects
        """
        # Build lookup from defect id to reviewer defect
        rev_lookup: Dict[str, Defect] = {}
        for output in reviewer_outputs:
            for defect in output.defects:
                rev_lookup[defect.id] = defect

        conflicts = []
        for cons_defect in consolidated:
            source_defects = [
                rev_lookup[sid] for sid in cons_defect.source_defect_ids
                if sid in rev_lookup
            ]
            if len(source_defects) < 2:
                continue

            # Check risk conflict
            risks = {d.risk.value for d in source_defects}
            if len(risks) > 1:
                conflicts.append(ConflictRecord(
                    defect_ids=cons_defect.source_defect_ids,
                    field="risk",
                    values=sorted(risks),
                    resolution=f"Resolved to {cons_defect.risk.value}",
                ))

            # Check fault_type conflict
            fault_types = {d.fault_type.value for d in source_defects}
            if len(fault_types) > 1:
                conflicts.append(ConflictRecord(
                    defect_ids=cons_defect.source_defect_ids,
                    field="fault_type",
                    values=sorted(fault_types),
                    resolution=f"Resolved to {cons_defect.fault_type.value}",
                ))

        return conflicts

    def _format_reviewer_outputs(self, outputs: List[ReviewerOutput]) -> str:
        """Format reviewer outputs for prompt.

        Args:
            outputs: List of reviewer outputs

        Returns:
            Formatted text
        """
        sections = []

        for output in outputs:
            sections.append(f"\n{'='*60}")
            sections.append(f"REVIEWER: {output.reviewer_id} ({output.technique.value})")
            sections.append(f"Found {len(output.defects)} defects")
            sections.append(f"{'='*60}\n")

            for i, defect in enumerate(output.defects, 1):
                sections.append(f"\nDefect #{i}:")
                sections.append(f"  Position: {defect.position}")
                sections.append(f"  Page: {defect.page_hint or 'N/A'}")
                sections.append(f"  Risk: {defect.risk.value}")
                sections.append(f"  Type: {defect.fault_type.value}")
                sections.append(f"  Description: {defect.description}")
                sections.append(f"  Evidence: {defect.evidence}")
                sections.append(f"  Confidence: {defect.confidence:.2f}")
                if defect.flags:
                    sections.append(f"  Flags: {', '.join(defect.flags)}")

            if output.notes:
                sections.append(f"\nNotes: {output.notes}")

        return "\n".join(sections)
