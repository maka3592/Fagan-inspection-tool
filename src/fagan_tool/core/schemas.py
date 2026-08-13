"""Core data schemas for the Fagan Inspection Tool."""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field, field_validator, model_validator


# Defect schema version for output standardization (Point 4)
# Increment when schema changes in a way that affects matching/evaluation
DEFECT_SCHEMA_VERSION = "1.1.0"


class RiskLevel(str, Enum):
    """Risk classification for defects."""

    A = "A"  # High risk
    B = "B"  # Medium risk
    C = "C"  # Low risk
    UNK = "UNK"  # Unknown


class FaultType(str, Enum):
    """Fault classification: Missing or Wrong."""

    M = "M"  # Missing
    W = "W"  # Wrong
    UNK = "UNK"  # Unknown


class ReadingTechnique(str, Enum):
    """Supported reading techniques."""

    UBR = "UBR"  # Usage-Based Reading
    CBR = "CBR"  # Checklist-Based Reading
    PBR_TESTER = "PBR_TESTER"  # Perspective-Based: Tester
    PBR_DESIGNER = "PBR_DESIGNER"  # Perspective-Based: Designer
    PBR_USER = "PBR_USER"  # Perspective-Based: User


class ConditionType(str, Enum):
    """Experimental conditions."""

    C1_UBR = "C1_UBR"
    C2_CBR = "C2_CBR"
    C3_PBR_TEAM = "C3_PBR_TEAM"
    C4_HYBRID = "C4_HYBRID"


class AgentRole(str, Enum):
    """Agent roles in the inspection process."""

    MODERATOR = "moderator"
    REVIEWER = "reviewer"
    SCRIBE = "scribe"
    AUTHOR = "author"


class Defect(BaseModel):
    """Individual defect/finding reported by a reviewer or meeting."""

    id: str = Field(description="Unique ID within the run")
    position: str = Field(description="Section, table, use case, or page reference")
    page_hint: Optional[str] = Field(default=None, description="Page number(s) where found")
    risk: RiskLevel = Field(default=RiskLevel.UNK)
    fault_type: FaultType = Field(default=FaultType.UNK)
    description: str = Field(description="Clear description of the defect")
    evidence: Union[str, Dict[str, Any]] = Field(description="Quote or paraphrase from artifact with page/section ref")
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)
    flags: List[str] = Field(default_factory=list, description="E.g., uncertain, needs_clarification")
    reviewer_id: Optional[str] = Field(default=None, description="Which reviewer found this")
    technique: Optional[ReadingTechnique] = Field(default=None)
    # Provenance fields (populated during meeting consolidation)
    source_defect_ids: List[str] = Field(
        default_factory=list,
        description="IDs of reviewer defects that were consolidated into this defect"
    )
    source_reviewer_ids: List[str] = Field(
        default_factory=list,
        description="Reviewer IDs that originally reported this defect"
    )
    source_techniques: List[str] = Field(
        default_factory=list,
        description="Reading techniques used by source reviewers"
    )
    original_position: Optional[str] = Field(
        default=None, description="Original position before inference"
    )
    # Position canonicalization fields (populated during meeting consolidation)
    position_canonical: Optional[str] = Field(
        default=None, description="Normalized canonical position used for matching"
    )
    position_mentions: List[str] = Field(
        default_factory=list,
        description="Section tokens found in description and evidence text"
    )
    position_autofixed: bool = Field(
        default=False, description="Whether position was auto-corrected from context"
    )
    position_autofix_reason: str = Field(
        default="", description="Reason for position autofix (e.g. single_mentioned_token)"
    )
    # ---------------------------------------------------------------
    # Inspection-Record quality fields (Defect Report Quality, 2026-05)
    # Added to lift report quality without touching matcher/metrics:
    # the matcher continues to read `position`, `description`, and the
    # legacy `evidence` dict. The five fields below are purely
    # informational + diagnostic; their absence is flagged but never
    # rejects a defect.
    # ---------------------------------------------------------------
    entity: Optional[str] = Field(
        default=None,
        description=(
            "Named entity from the artefact this defect references "
            "(signal / use-case / module name). Must be quoted exactly "
            "as written in the document."
        ),
    )
    expected: Optional[str] = Field(
        default=None,
        description="Short statement of what the artefact should specify (1-2 sentences).",
    )
    observed: Optional[str] = Field(
        default=None,
        description="Short statement of what the artefact actually specifies (1-2 sentences).",
    )
    evidence_location: Optional[str] = Field(
        default=None,
        description=(
            "Precise pointer into the artefact, e.g. 'p. 5, 3.4.1, MSC' "
            "or 'Table 1'. Derived from page_hint+position when omitted."
        ),
    )

    @field_validator("confidence")
    @classmethod
    def validate_confidence(cls, v: float) -> float:
        """Ensure confidence is in valid range."""
        return max(0.0, min(1.0, v))

    @model_validator(mode="after")
    def normalize_evidence(self) -> "Defect":
        """Normalize evidence to always be a dict object.

        If evidence is a string, convert to:
        {"quote_or_paraphrase": evidence, "page_hint": null}

        If evidence is missing/empty, set:
        {"quote_or_paraphrase": "", "page_hint": null}
        and mark defect as incomplete.
        """
        # If evidence is a string, normalize to dict
        if isinstance(self.evidence, str):
            evidence_str = self.evidence.strip()

            # If empty/missing evidence, mark as incomplete
            if not evidence_str:
                self.evidence = {
                    "quote_or_paraphrase": "",
                    "page_hint": None
                }
                if "incomplete" not in self.flags:
                    self.flags.append("incomplete")
            else:
                # Convert string to dict
                self.evidence = {
                    "quote_or_paraphrase": evidence_str,
                    "page_hint": self.page_hint  # Use existing page_hint if available
                }

        # If evidence is dict but missing keys, ensure structure
        elif isinstance(self.evidence, dict):
            if "quote_or_paraphrase" not in self.evidence:
                self.evidence["quote_or_paraphrase"] = self.evidence.get("quote", "")
            if "page_hint" not in self.evidence:
                self.evidence["page_hint"] = self.page_hint

            # Check if empty and mark incomplete
            if not self.evidence.get("quote_or_paraphrase", "").strip():
                if "incomplete" not in self.flags:
                    self.flags.append("incomplete")

        # Point 4: Validate position and description for output standardization
        # Empty/unknown position is flagged
        position_stripped = self.position.strip() if self.position else ""
        if not position_stripped or position_stripped.lower() == "unknown":
            if "missing_position" not in self.flags:
                self.flags.append("missing_position")

        # Empty description is flagged
        description_stripped = self.description.strip() if self.description else ""
        if not description_stripped:
            if "missing_description" not in self.flags:
                self.flags.append("missing_description")
            if "incomplete" not in self.flags:
                self.flags.append("incomplete")

        # ----- Inspection-record quality flags (2026-05) -----
        # We never reject defects on these; we only record what is missing
        # so downstream reporting and prompt-discipline checks can see it.
        def _is_blank(v: Optional[str]) -> bool:
            return not (v and v.strip())

        if _is_blank(self.entity) and "missing_entity" not in self.flags:
            self.flags.append("missing_entity")
        if _is_blank(self.expected) and "missing_expected" not in self.flags:
            self.flags.append("missing_expected")
        if _is_blank(self.observed) and "missing_observed" not in self.flags:
            self.flags.append("missing_observed")

        # Evidence quote — check the normalized dict (already populated above).
        ev_text = ""
        if isinstance(self.evidence, dict):
            ev_text = str(self.evidence.get("quote_or_paraphrase") or "").strip()
        if not ev_text and "missing_evidence" not in self.flags:
            self.flags.append("missing_evidence")

        # Deterministic evidence_location composition from page_hint+position.
        # This is pure formatting (no new information is invented): if a
        # reviewer omitted evidence_location we synthesise the pointer from
        # data the reviewer DID supply. Empty inputs leave the field empty
        # and trigger the missing_evidence_location flag.
        if _is_blank(self.evidence_location):
            page = (self.page_hint or "").strip()
            pos = (self.position or "").strip()
            if page and pos and pos.lower() != "unknown":
                self.evidence_location = f"{page}, {pos}"
            elif page:
                self.evidence_location = page
            elif pos and pos.lower() != "unknown":
                self.evidence_location = pos
        if _is_blank(self.evidence_location) and "missing_evidence_location" not in self.flags:
            self.flags.append("missing_evidence_location")

        return self


class ReviewerOutput(BaseModel):
    """Output from a single reviewer agent."""

    reviewer_id: str
    role: AgentRole = AgentRole.REVIEWER
    technique: ReadingTechnique
    defects: List[Defect] = Field(default_factory=list)
    notes: str = Field(default="")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    is_incomplete: bool = Field(default=False, description="True if output was truncated/failed")
    incomplete_reason: Optional[str] = Field(default=None, description="Reason for incomplete status")


class IncompleteDefect(BaseModel):
    """Defect that was rejected due to missing mandatory fields."""

    original_data: Dict[str, Any] = Field(description="Original defect data as reported")
    reason: str = Field(description="Why this defect is incomplete")
    reviewer_id: Optional[str] = None


class DuplicateGroup(BaseModel):
    """A group of reviewer defects that were merged into one consolidated defect."""

    canonical_id: str = Field(description="ID of the consolidated defect")
    merged_ids: List[str] = Field(description="IDs of source reviewer defects that were merged")
    reason: str = Field(default="Same position + similar description")
    position_tokens: List[str] = Field(default_factory=list)
    signal_tokens: List[str] = Field(default_factory=list)


class ConflictRecord(BaseModel):
    """A conflict between reviewer defects (e.g., different risk/fault_type)."""

    defect_ids: List[str] = Field(description="IDs of conflicting defects")
    field: str = Field(description="Field that conflicts (risk, fault_type)")
    values: List[str] = Field(description="The conflicting values")
    resolution: str = Field(default="", description="How the conflict was resolved")


class MeetingOutput(BaseModel):
    """Output from the inspection meeting (scribe agent)."""

    consolidated_defects: List[Defect] = Field(default_factory=list)
    incomplete_defects: List[IncompleteDefect] = Field(
        default_factory=list,
        description="Defects rejected due to missing mandatory fields"
    )
    duplicates_removed: int = Field(default=0)
    conflicts_flagged: int = Field(default=0)
    duplicate_groups: List[DuplicateGroup] = Field(
        default_factory=list,
        description="Deterministic duplicate group records"
    )
    conflicts: List[ConflictRecord] = Field(
        default_factory=list,
        description="Structured conflict records"
    )
    minutes: str = Field(description="Meeting minutes/summary")
    exit_decision: str = Field(description="Accept, Conditional Accept, or Reject")
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class LLMParams(BaseModel):
    """LLM parameters for reproducibility."""

    model: str
    provider: str  # "openai" or "anthropic"
    temperature: float = 0.2
    max_tokens: int = 4096
    top_p: Optional[float] = None
    extra: Dict[str, Any] = Field(default_factory=dict)


class ArtifactMetadata(BaseModel):
    """Metadata for input artifacts (NEVER include gold files)."""

    name: str
    path: str
    type: str  # "design", "usecase", "requirements", "guide"
    page_count: Optional[int] = None
    size_bytes: Optional[int] = None


class InspectionConfig(BaseModel):
    """Configuration for a single inspection run."""

    inspection_id: str = Field(description="Unique run identifier")
    condition: ConditionType
    reading_techniques: List[ReadingTechnique]
    artifacts: List[str] = Field(description="Paths to input artifacts (relative to artifacts/input/)")
    llm_params: LLMParams
    prompt_versions: Dict[str, str] = Field(
        default_factory=dict, description="Prompt file hashes or versions"
    )
    dry_run: bool = Field(default=False)
    extra_config: Dict[str, Any] = Field(default_factory=dict)


class RunMetadata(BaseModel):
    """Complete metadata for an inspection run."""

    inspection_id: str
    condition: ConditionType
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    llm_params: LLMParams
    artifacts_used: List[ArtifactMetadata] = Field(default_factory=list)
    prompt_versions: Dict[str, str] = Field(default_factory=dict)
    phase_completed: List[str] = Field(default_factory=list)
    # Follow-Up phase metrics (optional for backward compatibility)
    logs_complete: Optional[bool] = Field(
        default=None,
        description="True if no incomplete defects exist after follow-up"
    )
    evidence_quality: Optional[str] = Field(
        default=None,
        description="Overall evidence quality: 'high', 'medium', or 'low'"
    )
    incomplete_defects_count: Optional[int] = Field(
        default=None,
        description="Number of defects rejected due to missing mandatory fields"
    )
    # UBR-specific metadata (Point 2: use-case-driven inspection)
    ubr_variant: Optional[str] = Field(
        default=None,
        description="UBR variant: 'RB-UBR' (rank-based) or 'TC-UBR' (time-controlled)"
    )
    ubr_use_case_source: Optional[str] = Field(
        default=None,
        description="Path to use case artifact used for UBR inspection"
    )
    ubr_use_case_count: Optional[int] = Field(
        default=None,
        description="Number of use cases provided for inspection"
    )
    ubr_time_budgets: Optional[Dict[str, int]] = Field(
        default=None,
        description="Time budgets per use case (TC-UBR only), e.g. {'UC1.1': 8, 'UC1.2': 6}"
    )
    ubr_tc_budgets_detected: Optional[bool] = Field(
        default=None,
        description="TC-UBR only: True if time budgets were provided, False if missing (warning)"
    )
    # Point 3: Reviewer-specific artifact assignment tracking
    reviewer_artifacts_assigned: Optional[Dict[str, List[str]]] = Field(
        default=None,
        description="Per-reviewer artifact assignment, e.g. {'reviewer_1_ubr': ['design/X.pdf', 'usecase/Y.pdf']}"
    )
    # Point 4: Output standardization and gold isolation
    defect_schema_version: Optional[str] = Field(
        default=None,
        description="Version of defect schema used (e.g. '1.1.0')"
    )
    gold_guard_verified: Optional[bool] = Field(
        default=None,
        description="True if gold/fault artifacts were verified as blocked from reviewer context"
    )


# Valid UBR variant values (for validation)
VALID_UBR_VARIANTS = {"RB-UBR", "TC-UBR"}


# Reviewer Artifact Policy (Point 3: reviewer-specific input assignment)
# Each technique defines which artifact types are required, optional, or forbidden.
# Types are inferred from path/filename by ArtifactLoader._infer_type()
REVIEWER_ARTIFACT_POLICY = {
    ReadingTechnique.UBR: {
        "required_types": {"design"},        # Must have design document
        "optional_types": {"usecase", "guide", "requirements"},
        "forbidden_types": set(),            # No special restrictions beyond gold
    },
    ReadingTechnique.CBR: {
        "required_types": {"design"},        # Must have design document
        "optional_types": {"checklist", "usecase", "requirements"},
        "forbidden_types": set(),
    },
    ReadingTechnique.PBR_TESTER: {
        "required_types": {"design"},        # Must have design for testability analysis
        "optional_types": {"requirements", "usecase"},
        "forbidden_types": set(),
    },
    ReadingTechnique.PBR_DESIGNER: {
        "required_types": {"design"},        # Must have design for implementability
        "optional_types": {"requirements"},
        "forbidden_types": set(),
    },
    ReadingTechnique.PBR_USER: {
        "required_types": {"design"},        # Must have design
        "optional_types": {"usecase", "requirements"},  # Use cases strongly recommended
        "forbidden_types": set(),
    },
}


class InspectionRun(BaseModel):
    """Complete inspection run data."""

    metadata: RunMetadata
    config_snapshot: InspectionConfig
    reviewer_outputs: List[ReviewerOutput] = Field(default_factory=list)
    meeting_output: Optional[MeetingOutput] = None
    final_defects: List[Defect] = Field(default_factory=list)


class GoldDefect(BaseModel):
    """Defect from gold standard."""

    id: str
    position: str
    risk: RiskLevel
    fault_type: FaultType
    description: str
    section: Optional[str] = None
    page: Optional[str] = None


class MatchType(str, Enum):
    """Types of matches between found and gold defects."""

    EXACT = "exact"
    PARTIAL = "partial"
    DUPLICATE = "duplicate"
    NO_MATCH_POTENTIAL_NEW = "no_match_potential_new"
    NO_MATCH_FALSE_POSITIVE = "no_match_false_positive"


class DefectMatch(BaseModel):
    """Match between a found defect and gold standard."""

    found_id: str
    gold_id: Optional[str] = None
    match_type: MatchType
    similarity_score: float = Field(ge=0.0, le=1.0)
    notes: str = Field(default="")
    # Debug fields for diagnosing match/no-match outcomes
    best_candidate_gold_id: Optional[str] = Field(default=None)
    best_candidate_gold_position: Optional[str] = Field(default=None)
    best_candidate_similarity: float = Field(default=0.0, ge=0.0, le=1.0)
    best_candidate_match_reason: str = Field(default="no_candidates")


class EvaluationThresholds(BaseModel):
    """Threshold configuration for pass/fail evaluation."""

    min_recall: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Minimum recall threshold for pass"
    )
    min_precision: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Minimum precision threshold for pass"
    )
    min_f1: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Minimum F1 score threshold for pass"
    )
    min_recall_risk_a: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Minimum recall for high-risk (A) defects"
    )


class EvaluationMetadata(BaseModel):
    """Metadata about the evaluation process itself."""

    gold_standard_path: str = Field(description="Path to gold standard file used")
    gold_defect_count: int = Field(description="Number of defects in gold standard")
    matcher_thresholds: Dict[str, float] = Field(
        default_factory=dict,
        description="Matching thresholds used (description, exact, etc.)"
    )
    evaluation_version: str = Field(
        default="1.0.0",
        description="Version of evaluation algorithm"
    )
    defects_file_used: str = Field(
        default="final_defects.json",
        description="Which defects file was evaluated (final_defects.json or final_defects_gold_aligned.json)"
    )
    union_position_matching: bool = Field(
        default=True,
        description="Whether matcher uses union of position/original_position/position_canonical tokens"
    )


class EvaluationMetrics(BaseModel):
    """Evaluation metrics for a run."""

    run_id: str
    total_found: int
    total_gold: int
    true_positives: int
    true_positives_exact: int = Field(
        default=0,
        description="True positives with similarity >= 0.85 (exact matches)"
    )
    true_positives_partial: int = Field(
        default=0,
        description="True positives with threshold <= similarity < 0.85 (partial matches)"
    )
    false_positives: int
    false_positives_in_scope: int = Field(
        default=0,
        description="False positives within gold standard scope (Design/MSC)"
    )
    false_positives_out_of_scope: int = Field(
        default=0,
        description="False positives outside gold standard scope (e.g., Use Cases)"
    )
    false_negatives: int
    duplicates: int
    precision: float = Field(ge=0.0, le=1.0)
    precision_in_scope: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Precision considering only in-scope defects"
    )
    recall: float = Field(ge=0.0, le=1.0)
    f1_score: float = Field(ge=0.0, le=1.0)
    recall_by_risk: Dict[str, float] = Field(default_factory=dict)
    avg_findings_per_reviewer: float = Field(default=0.0)
    # TP similarity score statistics
    similarity_score_mean_tp: float = Field(
        default=0.0,
        description="Mean similarity score for true positives"
    )
    similarity_score_min_tp: float = Field(
        default=0.0,
        description="Minimum similarity score for true positives"
    )
    similarity_score_max_tp: float = Field(
        default=0.0,
        description="Maximum similarity score for true positives"
    )
    match_threshold: float = Field(
        default=0.6,
        description="The similarity threshold used for matching"
    )
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    # New fields for enhanced evaluation
    thresholds: Optional[EvaluationThresholds] = Field(
        default=None,
        description="Thresholds used for pass/fail determination"
    )
    passed: Optional[bool] = Field(
        default=None,
        description="Whether the evaluation passed all thresholds"
    )
    threshold_results: Dict[str, bool] = Field(
        default_factory=dict,
        description="Individual threshold pass/fail results"
    )
    evaluation_metadata: Optional[EvaluationMetadata] = Field(
        default=None,
        description="Metadata about the evaluation process"
    )
