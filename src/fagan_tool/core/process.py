"""Fagan inspection process orchestration."""

import json
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

console = Console()


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
        else:
            self.provider = None

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
        artifacts = self._load_artifacts()
        metadata.artifacts_used = [a["metadata"] for a in artifacts]

        if not self.config.dry_run:
            planning = self.moderator.plan_inspection(artifacts, self.config.condition.value)
            console.print(f"  Entry check: {planning.get('entry_check', 'Pass')}")
            console.print(f"  Focus areas: {', '.join(planning.get('focus_areas', []))}")
        else:
            planning = {"entry_check": "Pass (dry run)", "focus_areas": ["All"]}

        metadata.phase_completed.append("planning")

        # Phase 2: Kick-Off
        console.print("\n[bold]Phase 2: Kick-Off[/bold]")
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

                reviewer = ReviewerAgent(
                    self.provider,
                    reviewer_id,
                    technique,
                    self.prompt_dir,
                    debug_dir=self.output_dir,
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

        return "\n".join(context_parts)

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
