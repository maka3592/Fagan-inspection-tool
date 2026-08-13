"""Fagan inspection process orchestration."""

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from ..agents import ModeratorAgent, ReviewerAgent, ScribeAgent
from ..agents.base_agent import BaseAgent
from ..providers import get_provider
from ..utils import ArtifactLoader
from ..utils.gold_aligned_filter import filter_gold_aligned, gold_aligned_summary
from ..utils.position_tokens import build_allowed_position_tokens
from .schemas import (
    ConditionType,
    InspectionConfig,
    InspectionRun,
    ReadingTechnique,
    ReviewerOutput,
    RunMetadata,
    VALID_UBR_VARIANTS,
    REVIEWER_ARTIFACT_POLICY,
    DEFECT_SCHEMA_VERSION,
)
from ..utils.leakage_guard import LeakageGuard
from ..utils.usage_logging import UsageLogger, load_cost_config

console = Console()


# Regex for the deterministic entity-from-description fallback. We match
# only descriptions that begin with a quoted token such as
#   "'Reject_Order': ..."  or  '"Confirm_Voice": ...'
# i.e. the convention the reviewer prompts already require. This is pure
# text extraction (no inference) — if the description does not start with
# a quoted token the fallback leaves the entity untouched.
_ENTITY_FROM_DESC_RE = re.compile(r"""^\s*['"]([^'"]{1,80})['"]\s*:""")

# Patterns for the PBR position-anchor fix. We only touch positions that
# match the requirements-spec subchapter style ("3.1.X" / "3.2.X"); these
# are the cases where the LLM mis-anchored a finding on the requirements
# numbering instead of the design section. To rewrite, we need a concrete
# design / MSC reference inside evidence_location: a 3.X.Y or 4.X token,
# or "Table 1".
_PBR_REQ_POSITION_RE = re.compile(r"^\s*(?:3\.1\.\d+|3\.2\.\d+)\s*$")
_DESIGN_POSITION_IN_TEXT_RE = re.compile(
    r"\b(3\.\d\.\d|4\.\d|Table\s+\d+)\b"
)


def _backfill_entity_from_description(defect) -> bool:
    """Set the defect's ``entity`` from a leading quoted token in its
    description.

    Returns ``True`` when an entity was actually backfilled. Does nothing
    when the entity is already populated, when the description is empty,
    or when no quoted prefix is present. The ``missing_entity`` flag is
    removed only on a successful backfill so flag accounting stays honest.

    Accepts both pydantic ``Defect`` instances (attribute access) and
    plain ``dict`` payloads (as they appear in ``reviewer_outputs.json``
    or ``final_defects.json`` before being re-hydrated). This dual mode
    means the helper can be applied uniformly to live model objects in
    the process pipeline and to dicts loaded from disk by post-hoc
    tools, without forcing callers to convert.
    """
    is_dict = isinstance(defect, dict)

    if is_dict:
        entity = defect.get("entity")
        description = defect.get("description") or ""
        flags = defect.get("flags")
        if flags is None:
            flags = []
            defect["flags"] = flags
    else:
        entity = getattr(defect, "entity", None)
        description = getattr(defect, "description", "") or ""
        flags = getattr(defect, "flags", None)
        if flags is None:
            flags = []

    if entity and str(entity).strip():
        return False
    if not description.strip():
        return False
    m = _ENTITY_FROM_DESC_RE.match(description)
    if not m:
        return False
    candidate = m.group(1).strip()
    if not candidate:
        return False

    if is_dict:
        defect["entity"] = candidate
        if "missing_entity" in flags:
            flags.remove("missing_entity")
    else:
        defect.entity = candidate
        if "missing_entity" in flags:
            flags.remove("missing_entity")
    return True


def _pbr_backfill_design_position_from_evidence_location(defect) -> bool:
    """Rewrite PBR positions that look like requirements IDs onto a
    design / MSC section pulled from ``evidence_location``.

    Background: PBR reviewers sometimes write ``position="3.1.23"`` —
    a requirements-spec reference — even though the gap they describe
    sits in a design section (e.g. ``3.4.1`` MSC). The gold standard
    only carries design-section positions, so the requirements-style
    position causes the matcher's position gate to drop the candidate
    before description similarity is ever considered.

    We only touch defects whose technique is PBR-* and whose position
    matches the requirements subchapter pattern ``^3\\.1\\.\\d+$`` /
    ``^3\\.2\\.\\d+$``. If ``evidence_location`` already contains a
    concrete design / MSC reference (``3.X.Y``, ``4.X`` or
    ``Table N``), we promote that to ``position`` and preserve the
    original requirements ref in ``original_position`` plus a flag
    ``position_backfilled_from_evidence_location`` for transparency.

    No design position is invented. If ``evidence_location`` carries no
    matching token, the defect is left untouched (honest accounting).

    Accepts both ``Defect`` instances and plain dicts.
    Returns ``True`` if the position was actually rewritten.
    """
    is_dict = isinstance(defect, dict)

    def _get(key, default=None):
        if is_dict:
            return defect.get(key, default)
        return getattr(defect, key, default)

    def _set(key, value):
        if is_dict:
            defect[key] = value
        else:
            setattr(defect, key, value)

    # Only PBR_* reviewers fall under this rule.
    technique = _get("technique")
    if hasattr(technique, "value"):
        technique = technique.value
    technique_str = str(technique or "").strip().upper()
    if not technique_str.startswith("PBR"):
        return False

    position = str(_get("position") or "").strip()
    if not position or not _PBR_REQ_POSITION_RE.match(position):
        return False

    evidence_location = str(_get("evidence_location") or "").strip()
    if not evidence_location:
        return False

    m = _DESIGN_POSITION_IN_TEXT_RE.search(evidence_location)
    if not m:
        return False

    new_position = m.group(1).strip()
    # Normalise "Table 1" spacing (regex allows "Table  1") to canonical "Table 1".
    if new_position.lower().startswith("table"):
        parts = new_position.split()
        new_position = f"Table {parts[-1]}" if len(parts) >= 2 else new_position
    if new_position == position:
        return False

    # Preserve original position only if not already set (don't clobber
    # information from earlier passes).
    existing_original = str(_get("original_position") or "").strip()
    if not existing_original:
        _set("original_position", position)

    _set("position", new_position)

    # Audit flag.
    if is_dict:
        flags = defect.get("flags")
        if flags is None:
            flags = []
            defect["flags"] = flags
    else:
        flags = getattr(defect, "flags", None)
        if flags is None:
            flags = []
            try:
                setattr(defect, "flags", flags)
            except Exception:
                pass
    if "position_backfilled_from_evidence_location" not in flags:
        flags.append("position_backfilled_from_evidence_location")
    return True


# ---------------------------------------------------------------------------
# PBR description normalisation (deterministic, no new facts)
# ---------------------------------------------------------------------------
#
# PBR reviewers tend to phrase findings in requirements-spec language
# ("not specified", "expected behavior not specified", "incomplete"),
# which scores poorly against the gold standard's design-/MSC-style
# vocabulary. The helper below ONLY rewrites already-present text into
# a more gold-near form. Nothing is invented; if there is no entity to
# anchor on, the description is left alone.
_PBR_ENTITY_PREFIX_RE = re.compile(r"""^\s*['"]([^'"]{1,80})['"]\s*:\s*""")
_PBR_MULTI_SPACE_RE = re.compile(r"\s{2,}")
_PBR_TRAILING_PERIOD_RE = re.compile(r"\.+\s*$")

# Ordered substitutions. Composite (more specific) patterns first so that
# the generic "not specified / not defined" → "is missing" does not eat
# the more specific phrasings before they fire.
_PBR_NORMALIZATION_RULES = [
    (re.compile(r"expected behavior[^.,;\n]{0,80}?(?:is\s+)?not specified", re.IGNORECASE),
     "expected behavior is missing"),
    (re.compile(r"timeout[^.,;\n]{0,80}?(?:is\s+)?not (?:specified|defined)", re.IGNORECASE),
     "timeout is missing"),
    (re.compile(r"parameters?[^.,;\n]{0,80}?(?:not fully defined|missing details)", re.IGNORECASE),
     "parameter details are missing"),
    (re.compile(r"response format[^.,;\n]{0,80}?(?:is\s+)?not specified", re.IGNORECASE),
     "response format is missing"),
    (re.compile(r"data structure[^.,;\n]{0,80}?(?:incomplete|missing field)", re.IGNORECASE),
     "data structure is incomplete (missing fields)"),
    (re.compile(r"\b(?:no|missing)\s+(?:acknowledgment|acknowledgement|feedback)\b", re.IGNORECASE),
     "missing acknowledgment"),
    (re.compile(r"\bis\s+not\s+(?:specified|defined)\b", re.IGNORECASE),
     "is missing"),
    (re.compile(r"\bnot\s+(?:specified|defined)\b", re.IGNORECASE),
     "is missing"),
    # "not clearly <verb>" hedge phrasings. Same standardisation as the
    # plain "not <verb>" rules above; covers the hedged form that PBR
    # reviewers tend to write when they sense a partial spec but are
    # unsure how to express it. Active and "is"-leading forms are
    # handled together. Adverbs like "clearly" disrupt the bare
    # "specified|defined" regex above, so we add a dedicated rule
    # instead of widening the existing patterns (avoids over-matching).
    (re.compile(
        r"\bis\s+not\s+clearly\s+(?:defined|specified|described|detailed|documented)\b",
        re.IGNORECASE,
    ), "is missing"),
    (re.compile(
        r"\bnot\s+clearly\s+(?:defined|specified|described|detailed|documented)\b",
        re.IGNORECASE,
    ), "is missing"),
    # Requirements-style "not detailed / described / documented"
    # variants. These are pure language standardisation; the surrounding
    # location adverbials ("in the design", "in the MSC", "in Table 1")
    # stay where they are.
    (re.compile(r"\bis\s+not\s+(?:detailed|described|documented)\b", re.IGNORECASE),
     "is missing"),
    (re.compile(r"\bnot\s+(?:detailed|described|documented)\b", re.IGNORECASE),
     "is missing"),
    # Active-voice "<subject> does not address/cover/specify/describe/state …"
    # and passive "is not addressed/covered/specified/described/stated …".
    # We rewrite only the verb cluster; the object clause that follows
    # ("what happens if …", "in the design", …) is preserved verbatim.
    (re.compile(r"\bdoes\s+not\s+(?:address|cover|specify|describe|state)\b", re.IGNORECASE),
     "is missing"),
    (re.compile(r"\bdoes\s+not\s+define\b", re.IGNORECASE),
     "is missing"),
    (re.compile(r"\bis\s+not\s+(?:addressed|covered|specified|described|stated)\b", re.IGNORECASE),
     "is missing"),
    # "does not provide (implementation) details" → "is missing details"
    # (specific first, so the generic "does not provide" below does not
    # eat the modifier). Then a generic "does not provide" → "is missing"
    # for the remaining bare forms.
    (re.compile(r"\bdoes\s+not\s+provide\s+(?:implementation\s+)?details\b", re.IGNORECASE),
     "is missing details"),
    (re.compile(r"\bdoes\s+not\s+provide\b", re.IGNORECASE),
     "is missing"),
    # "(is) missing the timeout" → "timeout is missing" (gold uses the
    # subject-first phrasing). The specific timeout rule runs before
    # the generic "lacks" → "is missing" rule below so the timeout
    # variant gets its preferred shape.
    (re.compile(r"\b(?:is\s+)?missing\s+the\s+timeout\b", re.IGNORECASE),
     "timeout is missing"),
    # "lacks X" → "is missing X". Placed at the end so earlier
    # specialised rules (e.g. the acknowledgment normaliser) see the
    # original token before the verb is rewritten. Otherwise "lacks
    # feedback" would cascade into "missing acknowledgment", which the
    # tests explicitly check against.
    (re.compile(r"\blacks\b", re.IGNORECASE),
     "is missing"),
]

# Leading location-noise patterns. The matcher already has `position` and
# `evidence_location` for cross-checking the place of the defect; if the
# PBR claim text additionally starts with "Section 3.3.1, …" / "In
# section 3.3.1, …" / "p. 5, …" we strip those — they dilute the
# description's vocabulary against the gold standard without adding
# information.
_PBR_LEADING_NOISE_PATTERNS = [
    re.compile(r"^in\s+section\s+\d+(?:\.\d+)*\s*[:,]?\s*", re.IGNORECASE),
    re.compile(r"^section\s+\d+(?:\.\d+)*\s*[:,]?\s*", re.IGNORECASE),
    re.compile(r"^p\.\s*\d+\s*[:,]?\s*", re.IGNORECASE),
]

_PBR_DESCRIPTION_MAX = 200


def _normalize_pbr_description(defect) -> bool:
    """Rewrite a PBR defect's ``description`` into a gold-near form.

    Source text is picked in this order: ``observed`` → ``evidence``
    (``quote_or_paraphrase`` if dict, else the raw string) → existing
    ``description``. Each of the rewrite rules in
    :data:`_PBR_NORMALIZATION_RULES` is applied case-insensitively. The
    rewritten claim is then re-emitted as ``"'<entity>': <claim>."``,
    capped at :data:`_PBR_DESCRIPTION_MAX` chars.

    Guarantees:

    - Only acts when ``technique`` starts with ``"PBR"``.
    - Only acts when ``entity`` is set (the entity backfill helper in
      this module typically takes care of that).
    - Never invents facts — every word in the new description originated
      in the defect's own text.
    - Adds the audit flag ``pbr_description_normalized`` ONLY when the
      description was actually changed.

    Accepts both pydantic ``Defect`` instances and dicts.

    Returns ``True`` iff ``description`` was rewritten.
    """
    is_dict = isinstance(defect, dict)

    def _get(key, default=None):
        if is_dict:
            return defect.get(key, default)
        return getattr(defect, key, default)

    def _set(key, value):
        if is_dict:
            defect[key] = value
        else:
            setattr(defect, key, value)

    # PBR-only gate.
    technique = _get("technique")
    if hasattr(technique, "value"):
        technique = technique.value
    if not str(technique or "").strip().upper().startswith("PBR"):
        return False

    entity = str(_get("entity") or "").strip()
    if not entity:
        return False

    observed = str(_get("observed") or "").strip()
    evidence = _get("evidence")
    ev_quote = ""
    if isinstance(evidence, dict):
        ev_quote = str(evidence.get("quote_or_paraphrase") or "").strip()
    elif isinstance(evidence, str):
        ev_quote = evidence.strip()
    description_orig = str(_get("description") or "").strip()

    source = observed or ev_quote or description_orig
    if not source:
        return False

    # Strip a leading "'<entity>':" from the source so we do not
    # double-prefix the entity in the rewritten description.
    m = _PBR_ENTITY_PREFIX_RE.match(source)
    claim = source[m.end():] if m else source

    # Strip leading location noise ("Section 3.3.1", "In section 3.x",
    # "p. 5") that repeats what `position` / `evidence_location` already
    # carry. Loop so a stacked noise prefix like "p. 5, Section 3.3.1, "
    # gets stripped in one pass.
    prev = None
    while prev != claim:
        prev = claim
        for noise_pat in _PBR_LEADING_NOISE_PATTERNS:
            stripped = noise_pat.sub("", claim, count=1)
            if stripped != claim:
                claim = stripped
                # Restart the loop so the patterns can chain.
                break

    for pattern, replacement in _PBR_NORMALIZATION_RULES:
        claim = pattern.sub(replacement, claim)

    claim = _PBR_MULTI_SPACE_RE.sub(" ", claim).strip()
    claim = _PBR_TRAILING_PERIOD_RE.sub("", claim).strip()
    if not claim:
        return False
    if len(claim) > _PBR_DESCRIPTION_MAX:
        claim = claim[:_PBR_DESCRIPTION_MAX].rstrip()

    new_description = f"'{entity}': {claim}."
    if new_description == description_orig:
        return False

    _set("description", new_description)

    if is_dict:
        flags = defect.get("flags")
        if flags is None:
            flags = []
            defect["flags"] = flags
    else:
        flags = getattr(defect, "flags", None)
        if flags is None:
            flags = []
            try:
                setattr(defect, "flags", flags)
            except Exception:
                pass
    if "pbr_description_normalized" not in flags:
        flags.append("pbr_description_normalized")
    return True


class FaganProcess:
    """Orchestrates the complete Fagan inspection process."""

    def __init__(
        self,
        config: InspectionConfig,
        output_dir: Path = Path("runs"),
        prompt_dir: Path = Path("prompts"),
        run_id_override: Optional[str] = None,
    ):
        """Initialize Fagan process.

        Args:
            config: Inspection configuration
            output_dir: Directory for run outputs
            prompt_dir: Directory containing prompts
            run_id_override: Optional override for run ID (instead of using config.inspection_id)
        """
        self.config = config

        # Generate unique run ID
        base_id = run_id_override if run_id_override else config.inspection_id
        self.run_id = self._generate_unique_run_id(output_dir, base_id)

        self.output_dir = output_dir / self.run_id
        self.output_dir.mkdir(parents=True, exist_ok=False)  # Should not exist after unique ID generation
        self.prompt_dir = prompt_dir

        # Initialize provider
        if not config.dry_run:
            self.provider = get_provider(config.llm_params)
            # Optionales Usage-/Kostenlogging für neue Runs anhängen.
            # Verändert bestehende Runs/Ergebnisse nicht; bei Fehlern wird
            # der Run nicht beeinträchtigt.
            self.usage_logger = self._init_usage_logger()
        else:
            self.provider = None
            self.usage_logger = None

        # Initialize artifact loader
        self.artifact_loader = ArtifactLoader()

        # Initialize agents (with debug_dir for error tracking)
        if not config.dry_run:
            self.moderator = ModeratorAgent(self.provider, self.prompt_dir)
            self.scribe = ScribeAgent(self.provider, self.prompt_dir, debug_dir=self.output_dir)
        else:
            self.moderator = None
            self.scribe = None

    def _generate_unique_run_id(self, output_dir: Path, base_id: str) -> str:
        """Generate a unique run ID by appending counter suffix if needed.

        Args:
            output_dir: Base output directory (runs/)
            base_id: Base inspection ID

        Returns:
            Unique run ID that doesn't conflict with existing runs
        """
        # Check if base_id directory exists
        target_dir = output_dir / base_id
        if not target_dir.exists():
            return base_id

        # Find next available counter suffix
        counter = 2
        while True:
            candidate_id = f"{base_id}_{counter:03d}"
            candidate_dir = output_dir / candidate_id
            if not candidate_dir.exists():
                console.print(
                    f"[yellow]Run directory '{base_id}' exists. Using '{candidate_id}' instead.[/yellow]"
                )
                return candidate_id
            counter += 1
            if counter > 999:
                raise RuntimeError(
                    f"Too many runs with base ID '{base_id}'. Please clean up old runs or use a different ID."
                )

    def _validate_ubr_config(self) -> None:
        """Validate UBR-specific configuration (fail fast).

        Raises:
            ValueError: If ubr_variant is invalid or use_case_artifact is missing/unreadable.
        """
        ubr_variant = self.config.extra_config.get("ubr_variant", "RB-UBR")
        use_case_artifact = self.config.extra_config.get("use_case_artifact", "")

        # Validate ubr_variant
        if ubr_variant not in VALID_UBR_VARIANTS:
            raise ValueError(
                f"Invalid ubr_variant '{ubr_variant}'. "
                f"Must be one of: {', '.join(sorted(VALID_UBR_VARIANTS))}"
            )

        # Validate use_case_artifact path exists (if specified)
        if use_case_artifact:
            artifact_path = Path("artifacts/input") / use_case_artifact

            # Gold leakage guard for use_case_artifact (Point 4 hardening)
            # Prevents path traversal attacks like "../gold/Faults_List.xls"
            LeakageGuard.validate_path(artifact_path)

            if not artifact_path.exists():
                raise ValueError(
                    f"UBR use_case_artifact not found: {artifact_path}. "
                    f"Ensure the file exists in artifacts/input/"
                )

        # Log UBR config info
        console.print(f"  [dim]UBR variant: {ubr_variant}[/dim]")
        if use_case_artifact:
            console.print(f"  [dim]Use case source: {use_case_artifact}[/dim]")

    def _filter_artifacts_for_reviewer(
        self,
        technique: ReadingTechnique,
        artifacts: List[Dict],
        reviewer_id: str,
    ) -> List[Dict]:
        """Filter artifacts based on reviewer technique policy (Point 3).

        Args:
            technique: Reading technique for this reviewer
            artifacts: All loaded artifacts
            reviewer_id: Reviewer identifier for logging

        Returns:
            Filtered list of artifacts for this reviewer

        Raises:
            ValueError: If required artifact types are missing
        """
        policy = REVIEWER_ARTIFACT_POLICY.get(technique)
        if not policy:
            # No policy defined: pass all artifacts (fallback)
            console.print(f"    [dim]No artifact policy for {technique.value}, using all artifacts[/dim]")
            return artifacts

        required_types = policy["required_types"]
        optional_types = policy["optional_types"]
        allowed_types = required_types | optional_types

        # Filter artifacts by type
        filtered = []
        found_types = set()

        for artifact in artifacts:
            artifact_type = artifact["metadata"].type
            artifact_path = artifact["metadata"].path

            # Point 4: Defensive leakage guard check on reviewer level (fail-fast)
            if LeakageGuard.is_gold_path(artifact_path):
                # Log blocked artifact (without content)
                console.print(
                    f"    [red]⚠ BLOCKED: Gold artifact '{artifact_path}' "
                    f"rejected for {reviewer_id}[/red]"
                )
                # Mark gold guard as triggered (gold attempted but blocked)
                if hasattr(self, "_gold_guard_verified"):
                    self._gold_guard_verified = True  # Still verified because blocked
                # Fail-fast: raise error to prevent silent continuation
                raise ValueError(
                    f"GOLD LEAKAGE BLOCKED: Artifact '{artifact_path}' is from gold/fault directory "
                    f"and cannot be passed to reviewer '{reviewer_id}'. "
                    "Check your config artifacts list."
                )

            if artifact_type in allowed_types:
                filtered.append(artifact)
                found_types.add(artifact_type)

        # Validate required artifacts are present
        missing_required = required_types - found_types
        if missing_required:
            raise ValueError(
                f"Reviewer {reviewer_id} ({technique.value}) missing required artifact types: "
                f"{', '.join(sorted(missing_required))}. "
                f"Found: {', '.join(sorted(found_types)) or 'none'}. "
                f"Check your config artifacts list."
            )

        return filtered

    def run(self) -> InspectionRun:
        """Execute complete inspection process.

        Returns:
            Complete inspection run data
        """
        # Clear any previous JSON parse errors
        BaseAgent.clear_json_parse_errors()

        console.print("\n[bold cyan]Starting Fagan Inspection Process[/bold cyan]")
        console.print(f"Run ID: {self.run_id}")
        console.print(f"Condition: {self.config.condition.value}")
        console.print(f"Dry Run: {self.config.dry_run}\n")

        # Initialize metadata
        metadata = RunMetadata(
            inspection_id=self.run_id,  # Use actual run_id (may have suffix)
            condition=self.config.condition,
            llm_params=self.config.llm_params,
            prompt_versions=self.config.prompt_versions,
        )

        # Point 4: Set defect schema version for output standardization
        metadata.defect_schema_version = DEFECT_SCHEMA_VERSION

        # Add UBR-specific metadata if UBR technique is used
        if ReadingTechnique.UBR in self.config.reading_techniques:
            # Validate UBR config (fail fast on invalid configuration)
            self._validate_ubr_config()

            metadata.ubr_variant = self.config.extra_config.get("ubr_variant", "RB-UBR")
            metadata.ubr_use_case_source = self.config.extra_config.get("use_case_artifact", "")
            # Count use cases if specified in config
            use_case_count = self.config.extra_config.get("use_case_count")
            if use_case_count:
                metadata.ubr_use_case_count = use_case_count
            # Add time budgets for TC-UBR
            if metadata.ubr_variant == "TC-UBR":
                time_budgets = self.config.extra_config.get("time_budgets", {})
                if time_budgets:
                    metadata.ubr_time_budgets = time_budgets
                    metadata.ubr_tc_budgets_detected = True
                else:
                    # TC-UBR without explicit time_budgets: warn and set flag
                    metadata.ubr_tc_budgets_detected = False
                    console.print(
                        "[yellow]⚠ TC-UBR mode without explicit time_budgets in config. "
                        "Reviewers will use time hints from use case titles if available.[/yellow]"
                    )

        # Phase 1: Planning
        console.print("[bold]Phase 1: Planning[/bold]")
        self._set_usage_context(phase="planning", reviewer_id="")
        artifacts = self._load_artifacts()
        metadata.artifacts_used = [a["metadata"] for a in artifacts]

        if not self.config.dry_run:
            planning = self.moderator.plan_inspection(artifacts, self.config.condition.value)
            console.print(f"  Entry check: {planning.get('entry_check', 'Pass')}")
            console.print(f"  Focus areas: {', '.join(planning.get('focus_areas', []))}")
        else:
            planning = {"entry_check": "Pass (dry run)", "focus_areas": ["All"]}

        # If a requirements document is among the artifacts, make sure the
        # planning focus areas explicitly call out Req↔Design consistency.
        # The moderator agent may or may not mention it on its own.
        if any(a["metadata"].type == "requirements" for a in artifacts):
            focus_areas = list(planning.get("focus_areas") or [])
            req_focus = "Requirements-to-Design consistency"
            if not any(req_focus.lower() in str(f).lower() for f in focus_areas):
                focus_areas.append(req_focus)
                planning["focus_areas"] = focus_areas
                console.print(f"  [dim]+ added focus: {req_focus}[/dim]")

        metadata.phase_completed.append("planning")

        # Phase 2: Kick-Off
        console.print("\n[bold]Phase 2: Kick-Off[/bold]")
        self._set_usage_context(phase="kickoff", reviewer_id="")
        if not self.config.dry_run:
            kickoff = self.moderator.conduct_kickoff(artifacts, [t.value for t in self.config.reading_techniques])
        else:
            kickoff = {"roles_assigned": True}
        console.print("  Roles assigned and rules clarified")
        metadata.phase_completed.append("kickoff")

        # Phase 3: Preparation (simulated)
        console.print("\n[bold]Phase 3: Preparation[/bold]")
        console.print("  Reading technique guides distributed")
        metadata.phase_completed.append("preparation")

        # Phase 4: Individual Inspection
        console.print("\n[bold]Phase 4: Individual Inspection[/bold]")
        reviewer_outputs = self._conduct_individual_inspections(artifacts)
        console.print(f"  {len(reviewer_outputs)} reviewers completed inspection")
        incomplete_reviewers = []
        for output in reviewer_outputs:
            status = ""
            if output.is_incomplete:
                status = " [red][INCOMPLETE][/red]"
                incomplete_reviewers.append(output.reviewer_id)
            console.print(
                f"    {output.reviewer_id} ({output.technique.value}): "
                f"{len(output.defects)} defects found{status}"
            )
        if incomplete_reviewers:
            console.print(f"  [yellow]⚠ {len(incomplete_reviewers)} reviewer(s) have incomplete outputs[/yellow]")
        metadata.phase_completed.append("individual_inspection")

        # Point 3: Track reviewer artifact assignments in metadata
        if hasattr(self, "_reviewer_artifacts_assigned") and self._reviewer_artifacts_assigned:
            metadata.reviewer_artifacts_assigned = self._reviewer_artifacts_assigned
            # Log artifact assignments
            for rid, paths in self._reviewer_artifacts_assigned.items():
                console.print(f"    [dim]{rid}: {len(paths)} artifacts assigned[/dim]")

        # Point 4: Mark gold guard as verified (filtering happened in _filter_artifacts_for_reviewer)
        if hasattr(self, "_gold_guard_verified"):
            metadata.gold_guard_verified = self._gold_guard_verified
            if self._gold_guard_verified:
                console.print("    [dim]Gold guard: verified (no gold artifacts in reviewer context)[/dim]")

        # Phase 5: Inspection Meeting
        console.print("\n[bold]Phase 5: Inspection Meeting[/bold]")
        # reviewer_id zurücksetzen, damit es nicht vom letzten Reviewer
        # auf die Meeting-/Scribe-Calls leakt; technique auf das run-weite
        # Label zurücksetzen.
        self._set_usage_context(
            phase="inspection_meeting",
            reviewer_id="",
            technique=getattr(self, "_run_technique_label", ""),
        )
        # Build allowed position tokens from artifact text for drift guard
        allowed_tokens = self._extract_allowed_position_tokens(artifacts)
        if allowed_tokens:
            console.print(f"  Position drift guard: {len(allowed_tokens)} valid tokens from artifacts")
        meeting_output = self._conduct_meeting(reviewer_outputs, allowed_position_tokens=allowed_tokens)
        console.print(f"  Consolidated: {len(meeting_output.consolidated_defects)} defects")
        console.print(f"  Duplicates removed: {meeting_output.duplicates_removed}")
        if meeting_output.incomplete_defects:
            console.print(f"  [yellow]Incomplete defects rejected: {len(meeting_output.incomplete_defects)}[/yellow]")
        console.print(f"  Exit decision: {meeting_output.exit_decision}")
        metadata.phase_completed.append("inspection_meeting")

        # Phase 6: Rework (simulated - just note what needs fixing)
        console.print("\n[bold]Phase 6: Rework[/bold]")
        console.print("  Change requests generated (see final_defects.json)")
        metadata.phase_completed.append("rework")

        # Phase 7: Follow-Up
        console.print("\n[bold]Phase 7: Follow-Up[/bold]")
        self._set_usage_context(
            phase="followup",
            reviewer_id="",
            technique=getattr(self, "_run_technique_label", ""),
        )
        if not self.config.dry_run:
            followup = self.moderator.follow_up(reviewer_outputs, meeting_output)
            # Logs complete = True only if no incomplete defects
            logs_complete = followup.get('logs_complete', 'Yes') and len(meeting_output.incomplete_defects) == 0
            console.print(f"  Logs complete: {logs_complete}")
            if not logs_complete and meeting_output.incomplete_defects:
                console.print(f"  [yellow]⚠ Incomplete defects need revision[/yellow]")
            console.print(f"  Evidence quality: {followup.get('evidence_quality', 'Good')}")
        else:
            followup = {"logs_complete": True, "exit_approved": True}
        metadata.phase_completed.append("followup")

        # Create run object
        run = InspectionRun(
            metadata=metadata,
            config_snapshot=self.config,
            reviewer_outputs=reviewer_outputs,
            meeting_output=meeting_output,
            final_defects=meeting_output.consolidated_defects,
        )

        # Save outputs
        self._save_run(run)

        console.print("\n[bold green]Inspection Complete![/bold green]")
        console.print(f"Results saved to: {self.output_dir}")

        return run

    def _load_artifacts(self) -> List[Dict]:
        """Load inspection artifacts.

        Returns:
            List of loaded artifacts
        """
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("Loading artifacts...", total=None)
            artifacts = self.artifact_loader.load_artifacts(self.config.artifacts)
            progress.update(task, completed=True)

        console.print(f"  Loaded {len(artifacts)} artifacts:")
        for artifact in artifacts:
            console.print(f"    - {self.artifact_loader.get_artifact_summary(artifact)}")

        return artifacts

    def _conduct_individual_inspections(self, artifacts: List[Dict]) -> List[ReviewerOutput]:
        """Conduct individual inspections by all reviewers.

        Args:
            artifacts: Loaded artifacts

        Returns:
            List of reviewer outputs
        """
        outputs = []
        # Track artifact assignments per reviewer (Point 3)
        self._reviewer_artifacts_assigned: Dict[str, List[str]] = {}
        # Point 4: Track gold guard verification
        self._gold_guard_verified = True  # Will be set False if gold artifact encountered

        if self.config.dry_run:
            # Generate dummy outputs
            return self._generate_dummy_reviewer_outputs()

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            for i, technique in enumerate(self.config.reading_techniques):
                reviewer_id = f"reviewer_{i + 1}_{technique.value.lower()}"
                task = progress.add_task(f"  {reviewer_id} inspecting...", total=None)

                # Usage-Kontext für diesen Reviewer setzen: reviewer_id und
                # die konkrete Technik dieses Reviewers; Phase ist die
                # individuelle Inspektion. Stabile, run-lokal eindeutige ID.
                self._set_usage_context(
                    phase="individual_inspection",
                    reviewer_id=reviewer_id,
                    technique=technique.value,
                )

                # Per-run record-quality mode: "warn" (default) just flags
                # missing expected/observed; "repair" enables ONE follow-up
                # LLM call per reviewer and drops still-incomplete defects.
                record_quality_mode = str(
                    self.config.extra_config.get("record_quality_mode", "warn")
                ).strip().lower() or "warn"

                reviewer = ReviewerAgent(
                    self.provider,
                    reviewer_id,
                    technique,
                    self.prompt_dir,
                    debug_dir=self.output_dir,
                    record_quality_mode=record_quality_mode,
                )

                # Point 3: Filter artifacts based on reviewer policy
                reviewer_artifacts = self._filter_artifacts_for_reviewer(
                    technique, artifacts, reviewer_id
                )

                # Track which artifacts this reviewer received
                self._reviewer_artifacts_assigned[reviewer_id] = [
                    a["metadata"].path for a in reviewer_artifacts
                ]

                # Load extra context (checklist, use cases, etc.)
                extra_context = self._get_extra_context(technique, reviewer_index=i)

                output = reviewer.inspect(reviewer_artifacts, extra_context)

                # Deterministic entity backfill (no halucination).
                # If a reviewer omitted `entity` but wrote a description like
                # "'Reject_Order': missing in MSC", we lift the quoted token
                # into the entity slot so downstream reporting has a name.
                # expected/observed/evidence_location are NEVER synthesised
                # — those remain the reviewer's responsibility per prompt.
                # Opt-in PBR description normalisation: deterministic
                # rewrite of requirements-style phrasings into the
                # design-/MSC-style vocabulary used by the gold standard.
                # Off by default; enabled via extra_config in the PBR
                # experiment configs.
                pbr_desc_normalize_enabled = bool(
                    self.config.extra_config.get("pbr_description_normalize", False)
                )
                backfilled = 0
                pbr_pos_fix = 0
                pbr_desc_norm = 0
                for d in output.defects:
                    if _backfill_entity_from_description(d):
                        backfilled += 1
                    # PBR-only: rewrite requirements-style positions
                    # (3.1.X / 3.2.X) onto a design ref from
                    # evidence_location when one is present. No design
                    # position is invented.
                    if _pbr_backfill_design_position_from_evidence_location(d):
                        pbr_pos_fix += 1
                    if pbr_desc_normalize_enabled and _normalize_pbr_description(d):
                        pbr_desc_norm += 1
                if backfilled:
                    console.print(
                        f"    [dim]entity backfilled from description for "
                        f"{backfilled}/{len(output.defects)} defect(s)[/dim]"
                    )
                if pbr_pos_fix:
                    console.print(
                        f"    [dim]PBR position re-anchored to design "
                        f"section for {pbr_pos_fix}/{len(output.defects)} "
                        "defect(s) (original kept in original_position)[/dim]"
                    )
                if pbr_desc_norm:
                    console.print(
                        f"    [dim]PBR description normalised "
                        f"(deterministic, no new facts) for "
                        f"{pbr_desc_norm}/{len(output.defects)} defect(s)[/dim]"
                    )

                outputs.append(output)

                progress.update(task, completed=True)

        return outputs

    def _conduct_meeting(
        self,
        reviewer_outputs: List[ReviewerOutput],
        allowed_position_tokens: Optional[set] = None,
    ):
        """Conduct inspection meeting.

        Args:
            reviewer_outputs: Outputs from reviewers
            allowed_position_tokens: Optional set of valid position tokens from artifacts

        Returns:
            MeetingOutput
        """
        if self.config.dry_run:
            return self._generate_dummy_meeting_output(reviewer_outputs)

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("  Consolidating findings...", total=None)
            meeting_output = self.scribe.consolidate(
                reviewer_outputs,
                allowed_position_tokens=allowed_position_tokens,
            )
            progress.update(task, completed=True)

        return meeting_output

    def _get_extra_context(self, technique: ReadingTechnique, reviewer_index: int = 0) -> str:
        """Get extra context for reading technique.

        If the config contains extra_config.reviewer_focus (a list of strings),
        the entry at reviewer_index is appended to the base context. This allows
        per-reviewer scope partitioning so that each reviewer covers different
        sections of the document.

        Args:
            technique: Reading technique
            reviewer_index: Zero-based index of the current reviewer

        Returns:
            Extra context string
        """
        base_context = ""

        # For CBR, load checklist from config or default path
        if technique == ReadingTechnique.CBR:
            checklist_rel = self.config.extra_config.get(
                "checklist_path", "artifacts/input/checklists/cbr_checklist_v2.yaml"
            )
            checklist_path = Path(checklist_rel)

            # Gold leakage guard for checklist_path (Point 4 hardening)
            LeakageGuard.validate_path(checklist_path)

            # Restrict to allowed file types
            allowed_extensions = {".yaml", ".yml", ".txt"}
            if checklist_path.suffix.lower() not in allowed_extensions:
                raise ValueError(
                    f"Invalid checklist file type '{checklist_path.suffix}'. "
                    f"Allowed: {', '.join(sorted(allowed_extensions))}"
                )

            if checklist_path.exists():
                with open(checklist_path, encoding="utf-8") as f:
                    base_context = f.read()

        # For UBR, build structured use-case-driven context
        elif technique == ReadingTechnique.UBR:
            base_context = self._build_ubr_context()

        # For PBR, role-specific guidance
        elif "PBR" in technique.value:
            base_context = f"Apply {technique.value} perspective throughout the review."

        # Append per-reviewer focus if configured
        reviewer_focus = self.config.extra_config.get("reviewer_focus", [])
        if reviewer_focus and reviewer_index < len(reviewer_focus):
            focus_text = reviewer_focus[reviewer_index]
            if focus_text:
                base_context = f"{base_context}\n\n{focus_text}" if base_context else focus_text

        return base_context

    def _build_ubr_context(self) -> str:
        """Build structured UBR context with use case information.

        Extracts UBR variant (RB-UBR or TC-UBR) and use case metadata from config.
        Provides structured guidance for use-case-driven inspection per Petersen ESEM'08.

        Returns:
            Structured UBR context string for the reviewer prompt.
        """
        ubr_variant = self.config.extra_config.get("ubr_variant", "RB-UBR")
        use_case_artifact = self.config.extra_config.get("use_case_artifact", "")

        context_parts = []

        # UBR variant header
        context_parts.append(f"## UBR Inspection Mode: {ubr_variant}")
        context_parts.append("")

        if ubr_variant == "TC-UBR":
            # Time-controlled UBR
            time_budgets = self.config.extra_config.get("time_budgets", {})
            if time_budgets:
                context_parts.append("### Time Budgets per Use Case (TC-UBR)")
                context_parts.append("Focus your inspection effort according to these time allocations:")
                for uc_id, minutes in time_budgets.items():
                    context_parts.append(f"  - {uc_id}: {minutes} minutes")
                context_parts.append("")
            else:
                context_parts.append("### TC-UBR Mode")
                context_parts.append("Time-controlled mode enabled. If time budgets are in the use case titles,")
                context_parts.append("allocate inspection effort proportionally to those budgets.")
                context_parts.append("")
        else:
            # Rank-based UBR (default)
            context_parts.append("### RB-UBR Mode (Rank-Based)")
            context_parts.append("Process use cases in the order they appear (priority order).")
            context_parts.append("Do not skip use cases; work through all of them systematically.")
            context_parts.append("")

        # Use case artifact reference
        if use_case_artifact:
            context_parts.append(f"### Use Case Source: {use_case_artifact}")
            context_parts.append("")

        # UBR methodology reminder (from Petersen ESEM'08)
        context_parts.append("### UBR Inspection Process")
        context_parts.append("1. Start with the first (highest-priority) use case.")
        context_parts.append("2. Trace through the design document following the Tasks of the use case.")
        context_parts.append("3. Check if the design provides complete and correct information for the use case goal.")
        context_parts.append("4. Record defects where the design fails to support the use case.")
        context_parts.append("5. Proceed to the next use case and repeat.")
        context_parts.append("")
        context_parts.append("Use the Purpose, Tasks, and Variants of each use case as your analysis basis.")

        # Optional: append deterministic, heuristically extracted worklist
        # produced offline by scripts/extract_use_cases_rankbased.py. The
        # JSON lives next to the use case PDF (it is INPUT, not result).
        worklist_path = Path("artifacts/input/usecases/UseCasesRank_v3.4_extracted.json")
        worklist = self._render_extracted_use_case_worklist(worklist_path)
        if worklist:
            context_parts.append("")
            context_parts.append(worklist)
        elif not worklist_path.exists():
            # Not a hard failure — UBR works without the extracted worklist,
            # but reviewers benefit from a deterministic task list. Tell the
            # user how to produce it without leaving the project.
            console.print(
                f"[yellow]⚠ UBR worklist not found at {worklist_path}. "
                "Run `python scripts/extract_use_cases_rankbased.py` to generate it; "
                "UBR will continue without the extracted worklist for now.[/yellow]"
            )

        return "\n".join(context_parts)

    def _render_extracted_use_case_worklist(
        self,
        json_path: Path = Path(
            "artifacts/input/usecases/UseCasesRank_v3.4_extracted.json"
        ),
    ) -> str:
        """Render the extracted use-case worklist if the JSON is available.

        Returns an empty string when the file is missing or malformed; callers
        must treat that as "no worklist" and not raise. The JSON is produced
        by scripts/extract_use_cases_rankbased.py; we never reach the network
        and never invoke an LLM here.
        """
        if not json_path.exists():
            return ""
        try:
            import json as _json
            data = _json.loads(json_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return ""

        use_cases = data.get("use_cases") or []
        if not use_cases:
            return ""

        lines: List[str] = ["### Use Case Worklist (extracted)"]
        for uc in use_cases:
            uc_id = str(uc.get("id") or "?").strip()
            title = str(uc.get("title") or "").strip()
            header = f"- **{uc_id}**" + (f": {title}" if title else "")
            lines.append(header)
            tasks = uc.get("tasks") or []
            for t in tasks:
                t_str = str(t).strip()
                if t_str:
                    lines.append(f"    - Task: {t_str}")
            variants = uc.get("variants") or []
            for v in variants:
                v_str = str(v).strip()
                if v_str:
                    lines.append(f"    - Variant: {v_str}")
        warnings = data.get("warnings") or []
        if warnings:
            lines.append("")
            lines.append("_Extraction warnings: " + "; ".join(str(w) for w in warnings) + "_")
        return "\n".join(lines)

    def _extract_allowed_position_tokens(self, artifacts: List[Dict]) -> Optional[set]:
        """Extract the set of position tokens present in the artifact text.

        Collects all text from loaded artifacts and extracts valid position
        tokens (3.x, 4.x, Table N) to form the allowed set.

        Args:
            artifacts: Loaded artifact list from _load_artifacts()

        Returns:
            Set of allowed position tokens, or None if no text available.
        """
        all_text_parts = []
        for artifact in artifacts:
            content = artifact.get("content", {})
            content_type = content.get("type", "")
            if content_type == "pdf_pages":
                for page in content.get("pages", []):
                    all_text_parts.append(page.get("text", ""))
            elif content_type == "text":
                all_text_parts.append(content.get("text", ""))

        full_text = "\n".join(all_text_parts)
        if not full_text.strip():
            return None

        tokens = build_allowed_position_tokens(full_text)
        return tokens if tokens else None

    def _init_usage_logger(self) -> Optional[UsageLogger]:
        """Erzeugt einen UsageLogger und hängt ihn (mit Preis-Config) an den
        Provider. Robust: bei Fehlern wird kein Logger gesetzt und der Run
        läuft normal weiter."""
        try:
            cost_config = load_cost_config(Path("configs/llm_costs.yaml"))
            technique_label = ",".join(
                sorted({t.value for t in self.config.reading_techniques})
            ) or str(getattr(self.config.condition, "value", self.config.condition))
            # Run-weites Technik-Label merken, um es nach dem Reviewer-Loop
            # (der die konkrete Reviewer-Technik setzt) wiederherzustellen.
            self._run_technique_label = technique_label
            usage_logger = UsageLogger(
                context={"run_id": self.run_id, "technique": technique_label}
            )
            if self.provider is not None:
                self.provider.attach_usage_logger(usage_logger, cost_config)
            return usage_logger
        except Exception as exc:  # Logging ist optional, niemals fatal
            console.print(f"[yellow]Usage-Logger konnte nicht initialisiert werden: {exc}[/yellow]")
            return None

    def _set_usage_context(self, **kwargs) -> None:
        """Setzt Usage-Kontextfelder (phase, reviewer_id, technique, ...) am
        Provider/Logger. No-op bei dry_run (kein Provider) oder fehlendem
        Logger. ``reviewer_id=""`` setzt das Feld bewusst zurück, damit es
        nicht von Reviewer- auf Nicht-Reviewer-Calls leakt."""
        provider = getattr(self, "provider", None)
        if provider is None:
            return
        setter = getattr(provider, "set_call_context", None)
        if callable(setter):
            try:
                setter(**kwargs)
            except Exception:
                # Kontextsetzen darf einen Run niemals beeinträchtigen.
                pass

    def _write_usage_log(self) -> None:
        """Schreibt das Usage-Log pro Run und ergänzt das globale Log.

        Schreibt nur, wenn echte Call-Zeilen vorliegen. Überschreibt keine
        bestehenden Ergebnisdateien (globales Log wird angehängt)."""
        usage_logger = getattr(self, "usage_logger", None)
        if usage_logger is None or not usage_logger.rows:
            return
        try:
            usage_logger.write_csv(self.output_dir / "llm_usage.csv")
            global_log = Path("results") / "llm_usage_log.csv"
            usage_logger.write_csv(global_log, append=True)
        except Exception as exc:
            console.print(f"[yellow]Usage-Log konnte nicht geschrieben werden: {exc}[/yellow]")

    def _save_run(self, run: InspectionRun):
        """Save run outputs.

        Args:
            run: Inspection run data
        """
        # Save config snapshot
        with open(self.output_dir / "config_snapshot.json", "w") as f:
            json.dump(run.config_snapshot.model_dump(mode="json"), f, indent=2, default=str)

        # Save reviewer outputs
        with open(self.output_dir / "reviewer_outputs.json", "w") as f:
            json.dump(
                [r.model_dump(mode="json") for r in run.reviewer_outputs],
                f,
                indent=2,
                default=str,
            )

        # Save meeting output (including any JSON parse errors and incomplete reviewers)
        meeting_data = run.meeting_output.model_dump(mode="json")

        # Track JSON parse errors
        json_parse_errors = BaseAgent.get_json_parse_errors()
        if json_parse_errors:
            meeting_data["json_parse_errors"] = json_parse_errors
            console.print(f"  [yellow]⚠ {len(json_parse_errors)} JSON parse error(s) recorded[/yellow]")

        # Track incomplete reviewers
        incomplete_reviewers = [
            {
                "reviewer_id": r.reviewer_id,
                "reason": r.incomplete_reason or "Unknown",
                "defect_count": len(r.defects),
            }
            for r in run.reviewer_outputs if r.is_incomplete
        ]
        if incomplete_reviewers:
            meeting_data["incomplete_reviewers"] = incomplete_reviewers
            console.print(f"  [red]⚠ {len(incomplete_reviewers)} incomplete reviewer output(s)[/red]")

        # Position drift statistics
        drift_total = len(run.final_defects)
        drift_defects = [
            d for d in run.final_defects
            if d.position_autofixed or (
                d.original_position is not None and d.original_position != d.position
            )
        ]
        # Also count defects whose position_mentions disagree with position
        # (drift detected even if not autofixed)
        for d in run.final_defects:
            if d not in drift_defects and d.position_mentions:
                pos_tokens = set(d.position_canonical.split(", ")) if d.position_canonical else set()
                if pos_tokens and not (pos_tokens & set(d.position_mentions)):
                    drift_defects.append(d)

        drift_count = len(drift_defects)
        autofix_count = sum(1 for d in run.final_defects if d.position_autofixed)
        drift_rate = drift_count / drift_total if drift_total > 0 else 0.0

        drift_examples = [
            {
                "defect_id": d.id,
                "position_original": d.original_position or d.position,
                "position_canonical": d.position_canonical or d.position,
                "mentions": d.position_mentions,
                "description_prefix": d.description[:80],
            }
            for d in drift_defects[:10]
        ]

        meeting_data["position_drift_stats"] = {
            "position_drift_total": drift_total,
            "position_drift_count": drift_count,
            "position_drift_rate": round(drift_rate, 4),
            "position_autofix_count": autofix_count,
            "position_drift_examples": drift_examples,
        }

        if drift_count > 0:
            console.print(
                f"  [cyan]Position drift: {drift_count}/{drift_total} "
                f"({drift_rate:.1%}), autofixed: {autofix_count}[/cyan]"
            )
        else:
            console.print(f"  [dim]Position drift: 0/{drift_total} (clean)[/dim]")

        # Build gold-aligned subset and summary counts
        gold_aligned = filter_gold_aligned(run.final_defects)
        ga_summary = gold_aligned_summary(run.final_defects, gold_aligned)
        meeting_data["gold_aligned_summary"] = ga_summary

        console.print(
            f"  Gold-aligned: {ga_summary['total_final_defects_gold_aligned']} / "
            f"{ga_summary['total_final_defects_all']} "
            f"(novel: {ga_summary['total_novel_defects']})"
        )

        with open(self.output_dir / "meeting_output.json", "w") as f:
            json.dump(meeting_data, f, indent=2, default=str)

        # Save final defects (ALL_FOUND — complete set)
        with open(self.output_dir / "final_defects.json", "w") as f:
            json.dump(
                [d.model_dump(mode="json") for d in run.final_defects],
                f,
                indent=2,
                default=str,
            )

        # Save gold-aligned defects (filtered subset for evaluation vs gold)
        with open(self.output_dir / "final_defects_gold_aligned.json", "w") as f:
            json.dump(
                [d.model_dump(mode="json") for d in gold_aligned],
                f,
                indent=2,
                default=str,
            )

        # Save metadata
        with open(self.output_dir / "metadata.json", "w") as f:
            json.dump(run.metadata.model_dump(mode="json"), f, indent=2, default=str)

        # LLM-Usage-Log schreiben (nur bei echten Calls; siehe
        # docs/LLM_USAGE_LOGGING.md).
        self._write_usage_log()

    def _generate_dummy_reviewer_outputs(self) -> List[ReviewerOutput]:
        """Generate dummy reviewer outputs for dry run."""
        from ..core.schemas import Defect, FaultType, RiskLevel

        outputs = []
        for i, technique in enumerate(self.config.reading_techniques):
            reviewer_id = f"reviewer_{i + 1}_{technique.value.lower()}"
            defects = [
                Defect(
                    id=f"{reviewer_id}_dummy_{j}",
                    position=f"Section {j + 1}",
                    page_hint=f"p. {j + 3}",
                    risk=RiskLevel.B,
                    fault_type=FaultType.M,
                    description=f"Dummy defect {j + 1} from {technique.value}",
                    evidence=f"Simulated evidence (dry run)",
                    confidence=0.8,
                    reviewer_id=reviewer_id,
                    technique=technique,
                )
                for j in range(3)
            ]
            outputs.append(
                ReviewerOutput(
                    reviewer_id=reviewer_id,
                    technique=technique,
                    defects=defects,
                    notes="Dry run - simulated output",
                )
            )
        return outputs

    def _generate_dummy_meeting_output(self, reviewer_outputs: List[ReviewerOutput]):
        """Generate dummy meeting output for dry run."""
        from ..core.schemas import MeetingOutput

        all_defects = []
        for output in reviewer_outputs:
            all_defects.extend(output.defects)

        return MeetingOutput(
            consolidated_defects=all_defects[:5],  # Simulate consolidation
            duplicates_removed=len(all_defects) - 5,
            conflicts_flagged=1,
            minutes="Dry run - simulated meeting consolidation",
            exit_decision="Conditional Accept (dry run)",
        )
