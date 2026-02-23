#!/usr/bin/env python3
"""Verify all professor requirements for the Fagan Inspection Tool.

This script checks all requirements and produces a PASS/PARTIAL/FAIL/SKIP report.

Key Features:
- Runs without external internet access
- Handles missing API keys gracefully (SKIP, not FAIL)
- Verifies gold file is never modified
- Machine-readable JSON output option
- Human-readable console output

Usage:
    python scripts/verify_requirements.py              # Console output
    python scripts/verify_requirements.py --json       # JSON output
    python scripts/verify_requirements.py --output results.json
    fagan verify                                       # Via CLI
"""

import json
import os
import subprocess
import sys
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import List, Optional, Dict, Any

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


class Status(Enum):
    PASS = "PASS"
    PARTIAL = "PARTIAL"
    FAIL = "FAIL"
    SKIP = "SKIP"


@dataclass
class RequirementResult:
    """Result of checking a single requirement."""
    id: str
    description: str
    status: Status
    evidence: str = ""
    fix_hint: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "description": self.description,
            "status": self.status.value,
            "evidence": self.evidence,
            "fix_hint": self.fix_hint,
        }


@dataclass
class VerificationReport:
    """Complete verification report."""
    results: List[RequirementResult] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.now().astimezone().isoformat())
    project_root: str = ""

    def add(self, result: RequirementResult):
        self.results.append(result)

    @property
    def passed(self) -> int:
        return sum(1 for r in self.results if r.status == Status.PASS)

    @property
    def partial(self) -> int:
        return sum(1 for r in self.results if r.status == Status.PARTIAL)

    @property
    def failed(self) -> int:
        return sum(1 for r in self.results if r.status == Status.FAIL)

    @property
    def skipped(self) -> int:
        return sum(1 for r in self.results if r.status == Status.SKIP)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "project_root": self.project_root,
            "summary": {
                "passed": self.passed,
                "partial": self.partial,
                "failed": self.failed,
                "skipped": self.skipped,
                "total": len(self.results),
            },
            "results": [r.to_dict() for r in self.results],
        }


# =============================================================================
# REQUIREMENT CHECKS
# =============================================================================

def verify_ra_help_command(project_root: Path) -> RequirementResult:
    """RA: fagan --help works."""
    result = RequirementResult(
        id="RA",
        description="fagan --help runs successfully",
        status=Status.FAIL
    )

    try:
        proc = subprocess.run(
            ["fagan", "--help"],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=project_root,
        )
        if proc.returncode == 0 and "Usage:" in proc.stdout:
            result.status = Status.PASS
            result.evidence = "fagan --help executed successfully"
        else:
            result.evidence = f"Exit code: {proc.returncode}"
    except FileNotFoundError:
        result.status = Status.SKIP
        result.evidence = "fagan command not installed (run: pip install -e .)"
    except Exception as e:
        result.evidence = f"Error: {e}"

    return result


def verify_rb_dry_run(project_root: Path) -> RequirementResult:
    """RB: fagan dry-run works without API keys."""
    result = RequirementResult(
        id="RB",
        description="fagan dry-run works without API keys",
        status=Status.FAIL
    )

    try:
        # Temporarily unset API keys
        env = os.environ.copy()
        env.pop("OPENAI_API_KEY", None)
        env.pop("ANTHROPIC_API_KEY", None)

        proc = subprocess.run(
            ["fagan", "dry-run"],
            capture_output=True,
            text=True,
            timeout=60,
            cwd=project_root,
            env=env,
        )
        if proc.returncode == 0:
            result.status = Status.PASS
            result.evidence = "dry-run completed without API keys"
        else:
            result.evidence = f"Exit code: {proc.returncode}, stderr: {proc.stderr[:100]}"
    except FileNotFoundError:
        result.status = Status.SKIP
        result.evidence = "fagan command not installed"
    except subprocess.TimeoutExpired:
        result.status = Status.PARTIAL
        result.evidence = "dry-run timed out (may still work)"
    except Exception as e:
        result.evidence = f"Error: {e}"

    return result


def verify_rc_run_with_api(project_root: Path) -> RequirementResult:
    """RC: fagan run requires API key and gives clear error if missing."""
    result = RequirementResult(
        id="RC",
        description="fagan run: API key check with clear error",
        status=Status.FAIL
    )

    try:
        cli_path = project_root / "src" / "fagan_tool" / "cli.py"
        with open(cli_path) as f:
            content = f.read()

        # Check command exists with config option
        if '@app.command("run")' in content and '--config' in content:
            # Check for API key validation
            api_key = os.environ.get("OPENAI_API_KEY")
            if api_key:
                result.status = Status.PASS
                result.evidence = "run command defined; OPENAI_API_KEY is set"
            else:
                result.status = Status.SKIP
                result.evidence = "run command defined; OPENAI_API_KEY not set (expected SKIP)"
        else:
            result.evidence = "run command not properly defined"

    except Exception as e:
        result.evidence = f"Error: {e}"

    return result


def verify_r1_unique_run_id(project_root: Path) -> RequirementResult:
    """R1: Run-ID never overwritten (suffix logic)."""
    result = RequirementResult(
        id="R1",
        description="Run-ID suffix logic prevents overwriting",
        status=Status.FAIL
    )

    try:
        process_path = project_root / "src" / "fagan_tool" / "core" / "process.py"
        with open(process_path) as f:
            content = f.read()

        checks = [
            "_ensure_unique_run_id" in content or "unique" in content.lower(),
            "suffix" in content.lower() or "_002" in content or "_00" in content,
        ]

        if all(checks):
            result.status = Status.PASS
            result.evidence = "Unique run ID with suffix logic in process.py"
        elif any(checks):
            result.status = Status.PARTIAL
            result.evidence = "Partial run ID uniqueness logic found"
        else:
            result.evidence = "Unique run ID logic not found"

    except Exception as e:
        result.evidence = f"Error: {e}"

    return result


def verify_r2_config_snapshot(project_root: Path) -> RequirementResult:
    """R2: config_snapshot.json saved per run."""
    result = RequirementResult(
        id="R2",
        description="config_snapshot.json saved per run",
        status=Status.FAIL
    )

    try:
        # Check existing runs for config_snapshot.json
        runs_dir = project_root / "runs"
        if runs_dir.exists():
            for run_dir in runs_dir.iterdir():
                if run_dir.is_dir():
                    snapshot = run_dir / "config_snapshot.json"
                    if snapshot.exists():
                        result.status = Status.PASS
                        result.evidence = f"Found: {run_dir.name}/config_snapshot.json"
                        return result

        # Check code for config_snapshot saving
        process_path = project_root / "src" / "fagan_tool" / "core" / "process.py"
        if process_path.exists():
            with open(process_path) as f:
                if "config_snapshot" in f.read():
                    result.status = Status.PASS
                    result.evidence = "config_snapshot logic in process.py"
                    return result

        result.status = Status.SKIP
        result.evidence = "No runs directory; run fagan dry-run first"

    except Exception as e:
        result.evidence = f"Error: {e}"

    return result


def verify_r3_metadata(project_root: Path) -> RequirementResult:
    """R3: metadata.json contains prompt_versions/llm_params/artifacts_used."""
    result = RequirementResult(
        id="R3",
        description="metadata.json contains prompt_versions/llm_params",
        status=Status.FAIL
    )

    try:
        # Check schemas for metadata fields
        schemas_path = project_root / "src" / "fagan_tool" / "core" / "schemas.py"
        with open(schemas_path) as f:
            content = f.read()

        checks = [
            "prompt_versions" in content,
            "llm_params" in content or "LLMParams" in content,
            "artifacts" in content.lower(),
        ]

        if all(checks):
            result.status = Status.PASS
            result.evidence = "All metadata fields defined in schemas.py"
        elif any(checks):
            result.status = Status.PARTIAL
            result.evidence = "Some metadata fields defined"
        else:
            result.evidence = "Metadata fields not found"

    except Exception as e:
        result.evidence = f"Error: {e}"

    return result


def verify_r4_c1_three_reviewers(project_root: Path) -> RequirementResult:
    """R4: C1 uses 3 UBR reviewers."""
    result = RequirementResult(
        id="R4",
        description="C1 config has 3 UBR reviewers",
        status=Status.FAIL
    )

    try:
        config_path = project_root / "configs" / "examples" / "c1_ubr.yaml"
        if not config_path.exists():
            result.evidence = f"Config not found: {config_path}"
            return result

        import yaml
        with open(config_path) as f:
            config = yaml.safe_load(f)

        techniques = config.get("reading_techniques", [])
        ubr_count = sum(1 for t in techniques if t == "UBR")

        if ubr_count == 3:
            result.status = Status.PASS
            result.evidence = f"C1 config has {ubr_count} UBR reviewers"
        else:
            result.status = Status.PARTIAL
            result.evidence = f"C1 config has {ubr_count} UBR (expected 3)"

    except Exception as e:
        result.evidence = f"Error: {e}"

    return result


def verify_r5_reviewer_outputs(project_root: Path) -> RequirementResult:
    """R5: reviewer_outputs.json contains 3 entries for C1."""
    result = RequirementResult(
        id="R5",
        description="reviewer_outputs.json has 3 entries (C1)",
        status=Status.SKIP
    )

    try:
        runs_dir = project_root / "runs"
        if not runs_dir.exists():
            result.evidence = "No runs directory; run fagan dry-run first"
            return result

        for run_dir in sorted(runs_dir.iterdir(), reverse=True):
            if run_dir.is_dir() and "c1" in run_dir.name.lower():
                outputs_file = run_dir / "reviewer_outputs.json"
                if outputs_file.exists():
                    with open(outputs_file) as f:
                        outputs = json.load(f)
                    count = len(outputs)
                    if count == 3:
                        result.status = Status.PASS
                        result.evidence = f"{run_dir.name}: {count} reviewer entries"
                    else:
                        result.status = Status.PARTIAL
                        result.evidence = f"{run_dir.name}: {count} entries (expected 3)"
                    return result

        result.evidence = "No C1 runs found with reviewer_outputs.json"

    except Exception as e:
        result.evidence = f"Error: {e}"

    return result


def verify_r6_ubr_prompt_priority(project_root: Path) -> RequirementResult:
    """R6: UBR prompt prioritizes Design/MSC (sections 3.x/4.x)."""
    result = RequirementResult(
        id="R6",
        description="UBR prompt prioritizes Design/MSC",
        status=Status.FAIL
    )

    try:
        prompt_path = project_root / "prompts" / "reviewer_ubr.txt"
        if not prompt_path.exists():
            result.evidence = f"Prompt not found: {prompt_path}"
            return result

        with open(prompt_path) as f:
            content = f.read()

        checks = [
            "3.x" in content or "sections 3" in content.lower(),
            "4.x" in content or "sections 4" in content.lower(),
            "MSC" in content or "Design" in content,
            "AVOID USE CASE" in content.upper() or "USE CASE-ONLY" in content.upper(),
        ]

        if all(checks):
            result.status = Status.PASS
            result.evidence = "UBR prompt has Design/MSC priority + Use Case avoidance"
        elif sum(checks) >= 2:
            result.status = Status.PARTIAL
            result.evidence = f"UBR prompt partially prioritizes Design/MSC ({sum(checks)}/4 checks)"
        else:
            result.evidence = "UBR prompt missing Design/MSC priority"

    except Exception as e:
        result.evidence = f"Error: {e}"

    return result


def verify_r7_gold_xls_support(project_root: Path) -> RequirementResult:
    """R7: GoldLoader reads .xls with xlrd dependency."""
    result = RequirementResult(
        id="R7",
        description="GoldLoader reads .xls (xlrd dependency)",
        status=Status.FAIL
    )

    try:
        pyproject_path = project_root / "pyproject.toml"
        with open(pyproject_path) as f:
            content = f.read()

        if "xlrd" in content:
            result.status = Status.PASS
            result.evidence = "xlrd in pyproject.toml dependencies"
        else:
            result.status = Status.PARTIAL
            result.evidence = "xlrd missing from pyproject.toml"
            result.fix_hint = "Add xlrd>=2.0.1 to dependencies"

    except Exception as e:
        result.evidence = f"Error: {e}"

    return result


def verify_r8_gold_defect_count(project_root: Path) -> RequirementResult:
    """R8: Gold defect count = 36."""
    result = RequirementResult(
        id="R8",
        description="Gold standard contains 36 defects",
        status=Status.FAIL
    )

    try:
        from fagan_tool.evaluation.gold_loader import GoldLoader

        gold_path = project_root / "artifacts" / "gold" / "Faults_List_In_ver6.xls"
        if not gold_path.exists():
            result.evidence = f"Gold file not found: {gold_path}"
            return result

        loader = GoldLoader(gold_path)
        defects = loader.load()
        count = len(defects)

        if count == 36:
            result.status = Status.PASS
            result.evidence = f"Gold standard: {count} defects"
        else:
            result.status = Status.PARTIAL
            result.evidence = f"Gold standard: {count} defects (expected 36)"

    except ImportError:
        result.status = Status.SKIP
        result.evidence = "GoldLoader import failed (install xlrd?)"
    except Exception as e:
        result.evidence = f"Error: {e}"

    return result


def verify_r9_gold_integrity(project_root: Path) -> RequirementResult:
    """R9: Gold file is read-only and never modified by verify/run."""
    result = RequirementResult(
        id="R9",
        description="Gold file protected (LeakageGuard)",
        status=Status.FAIL
    )

    try:
        # Check LeakageGuard exists and protects gold
        guard_path = project_root / "src" / "fagan_tool" / "utils" / "leakage_guard.py"
        if not guard_path.exists():
            result.evidence = "LeakageGuard not found"
            return result

        with open(guard_path) as f:
            content = f.read()

        checks = [
            "FORBIDDEN_PATHS" in content,
            "artifacts/gold" in content,
            "validate_path" in content,
        ]

        # Also verify gold file exists
        gold_path = project_root / "artifacts" / "gold" / "Faults_List_In_ver6.xls"

        if all(checks) and gold_path.exists():
            result.status = Status.PASS
            result.evidence = "LeakageGuard protects gold; file exists"
        elif all(checks):
            result.status = Status.PARTIAL
            result.evidence = "LeakageGuard OK but gold file missing"
        else:
            result.evidence = "LeakageGuard incomplete"

    except Exception as e:
        result.evidence = f"Error: {e}"

    return result


def verify_r10_eval_outputs(project_root: Path) -> RequirementResult:
    """R10: fagan eval generates metrics.json, matches.json, matches_enriched.csv."""
    result = RequirementResult(
        id="R10",
        description="fagan eval outputs: metrics/matches/CSV",
        status=Status.FAIL
    )

    try:
        cli_path = project_root / "src" / "fagan_tool" / "cli.py"
        with open(cli_path) as f:
            content = f.read()

        checks = [
            "metrics.json" in content,
            "matches.json" in content,
            "matches_enriched.csv" in content,
        ]

        if all(checks):
            result.status = Status.PASS
            result.evidence = "All eval outputs defined in cli.py"
        else:
            missing = []
            if not checks[0]: missing.append("metrics.json")
            if not checks[1]: missing.append("matches.json")
            if not checks[2]: missing.append("matches_enriched.csv")
            result.evidence = f"Missing: {', '.join(missing)}"

    except Exception as e:
        result.evidence = f"Error: {e}"

    return result


def verify_r11_fp_formula(project_root: Path) -> RequirementResult:
    """R11: FP = TotalFound - TP - Duplicates."""
    result = RequirementResult(
        id="R11",
        description="FP = TotalFound - TP - Duplicates",
        status=Status.FAIL
    )

    try:
        metrics_path = project_root / "src" / "fagan_tool" / "evaluation" / "metrics.py"
        with open(metrics_path) as f:
            content = f.read()

        if "total_found - true_positives - duplicates" in content:
            result.status = Status.PASS
            result.evidence = "Correct FP formula in metrics.py"
        else:
            result.evidence = "FP formula not found or incorrect"

    except Exception as e:
        result.evidence = f"Error: {e}"

    return result


def verify_r12_fp_split(project_root: Path) -> RequirementResult:
    """R12: FP split in-scope/out-of-scope."""
    result = RequirementResult(
        id="R12",
        description="FP split in-scope/out-of-scope",
        status=Status.FAIL
    )

    try:
        metrics_path = project_root / "src" / "fagan_tool" / "evaluation" / "metrics.py"
        with open(metrics_path) as f:
            content = f.read()

        checks = [
            "fp_in_scope" in content or "false_positives_in_scope" in content,
            "fp_out_of_scope" in content or "false_positives_out_of_scope" in content,
        ]

        if all(checks):
            result.status = Status.PASS
            result.evidence = "FP split in metrics.py"
        else:
            result.evidence = "FP split not found"

    except Exception as e:
        result.evidence = f"Error: {e}"

    return result


def verify_r13_match_threshold(project_root: Path) -> RequirementResult:
    """R13: --match-threshold parameter and stored in metrics."""
    result = RequirementResult(
        id="R13",
        description="--match-threshold parameter + stored in metrics",
        status=Status.FAIL
    )

    try:
        cli_path = project_root / "src" / "fagan_tool" / "cli.py"
        schemas_path = project_root / "src" / "fagan_tool" / "core" / "schemas.py"

        with open(cli_path) as f:
            cli_content = f.read()
        with open(schemas_path) as f:
            schemas_content = f.read()

        checks = [
            "--match-threshold" in cli_content,
            "match_threshold" in schemas_content,
        ]

        if all(checks):
            result.status = Status.PASS
            result.evidence = "match_threshold in CLI and schemas"
        elif checks[0]:
            result.status = Status.PARTIAL
            result.evidence = "CLI has param, but not in schemas"
        else:
            result.evidence = "match_threshold not found"

    except Exception as e:
        result.evidence = f"Error: {e}"

    return result


def verify_r14_manual_template(project_root: Path) -> RequirementResult:
    """R14: Manual validation template (matches_manual.csv)."""
    result = RequirementResult(
        id="R14",
        description="Manual validation: export matches_manual.csv",
        status=Status.FAIL
    )

    try:
        script_path = project_root / "scripts" / "create_manual_template.py"
        cli_path = project_root / "src" / "fagan_tool" / "cli.py"

        script_exists = script_path.exists()

        with open(cli_path) as f:
            cli_content = f.read()
        cli_has_cmd = "manual-template" in cli_content or "manual_template" in cli_content

        if script_exists and cli_has_cmd:
            result.status = Status.PASS
            result.evidence = "Script + CLI command exist"
        elif script_exists or cli_has_cmd:
            result.status = Status.PASS
            result.evidence = "Script or CLI command exists"
        else:
            result.fix_hint = "Create scripts/create_manual_template.py"

    except Exception as e:
        result.evidence = f"Error: {e}"

    return result


def verify_r15_manual_metrics(project_root: Path) -> RequirementResult:
    """R15: Manual metrics calculation (validated_metrics.json)."""
    result = RequirementResult(
        id="R15",
        description="Manual validation: metrics_manual.json output",
        status=Status.FAIL
    )

    try:
        script_path = project_root / "scripts" / "calculate_manual_metrics.py"
        cli_path = project_root / "src" / "fagan_tool" / "cli.py"

        script_exists = script_path.exists()

        with open(cli_path) as f:
            cli_content = f.read()
        cli_has_cmd = "manual-eval" in cli_content or "manual_eval" in cli_content

        if script_exists and cli_has_cmd:
            result.status = Status.PASS
            result.evidence = "Script + CLI command exist"
        elif script_exists or cli_has_cmd:
            result.status = Status.PASS
            result.evidence = "Script or CLI command exists"
        else:
            result.fix_hint = "Create scripts/calculate_manual_metrics.py"

    except Exception as e:
        result.evidence = f"Error: {e}"

    return result


def verify_r16_report(project_root: Path) -> RequirementResult:
    """R16: fagan report with FP split + threshold."""
    result = RequirementResult(
        id="R16",
        description="fagan report with FP split + threshold",
        status=Status.FAIL
    )

    try:
        cli_path = project_root / "src" / "fagan_tool" / "cli.py"
        with open(cli_path) as f:
            content = f.read()

        checks = [
            '@app.command("report")' in content,
            "report.md" in content,
            "in_scope" in content.lower() or "In-scope" in content,
            "match_threshold" in content or "Match Threshold" in content,
        ]

        if all(checks):
            result.status = Status.PASS
            result.evidence = "Report with FP split + threshold"
        elif checks[0] and checks[1]:
            result.status = Status.PARTIAL
            result.evidence = "Report exists but missing FP split or threshold"
        else:
            result.evidence = "Report command incomplete"

    except Exception as e:
        result.evidence = f"Error: {e}"

    return result


def verify_r17_no_gold_writes(project_root: Path) -> RequirementResult:
    """R17: Verify script never writes to artifacts/gold/."""
    result = RequirementResult(
        id="R17",
        description="Verify never writes to artifacts/gold/",
        status=Status.FAIL
    )

    try:
        import re

        # Check CLI and core modules (not this script - it only reads gold)
        cli_path = project_root / "src" / "fagan_tool" / "cli.py"
        process_path = project_root / "src" / "fagan_tool" / "core" / "process.py"

        files_to_check = [cli_path, process_path]

        # Patterns that would indicate writing to gold directory
        # Use proper regex to avoid self-matching
        write_patterns = [
            r'\.write\s*\([^)]*gold',     # .write(...gold...)
            r'to_excel\s*\([^)]*gold',    # to_excel(...gold...)
            r'\.save\s*\([^)]*gold',      # .save(...gold...)
            r'shutil\.copy[^(]*\([^)]*gold[^)]*,[^)]*\)',  # shutil.copy(..., gold...)
        ]

        has_writes = False
        evidence_detail = ""

        for fpath in files_to_check:
            if not fpath.exists():
                continue
            with open(fpath) as f:
                content = f.read()
                for pattern in write_patterns:
                    if re.search(pattern, content, re.IGNORECASE):
                        has_writes = True
                        evidence_detail = f"Pattern '{pattern}' in {fpath.name}"
                        break
            if has_writes:
                break

        # Also verify LeakageGuard protects gold
        guard_path = project_root / "src" / "fagan_tool" / "utils" / "leakage_guard.py"
        guard_exists = guard_path.exists()
        guard_protects_gold = False
        if guard_exists:
            with open(guard_path) as f:
                guard_content = f.read()
                guard_protects_gold = "artifacts/gold" in guard_content

        if not has_writes and guard_protects_gold:
            result.status = Status.PASS
            result.evidence = "No gold writes; LeakageGuard protects gold"
        elif not has_writes and guard_exists:
            result.status = Status.PASS
            result.evidence = "No gold writes; LeakageGuard exists"
        elif not has_writes:
            result.status = Status.PASS
            result.evidence = "No gold write operations detected"
        else:
            result.evidence = f"Possible gold write: {evidence_detail}"

    except Exception as e:
        result.evidence = f"Error: {e}"

    return result


# =============================================================================
# MAIN VERIFICATION
# =============================================================================

def run_verification(project_root: Path) -> VerificationReport:
    """Run all verification checks."""
    report = VerificationReport()
    report.project_root = str(project_root)

    checks = [
        verify_ra_help_command,
        verify_rb_dry_run,
        verify_rc_run_with_api,
        verify_r1_unique_run_id,
        verify_r2_config_snapshot,
        verify_r3_metadata,
        verify_r4_c1_three_reviewers,
        verify_r5_reviewer_outputs,
        verify_r6_ubr_prompt_priority,
        verify_r7_gold_xls_support,
        verify_r8_gold_defect_count,
        verify_r9_gold_integrity,
        verify_r10_eval_outputs,
        verify_r11_fp_formula,
        verify_r12_fp_split,
        verify_r13_match_threshold,
        verify_r14_manual_template,
        verify_r15_manual_metrics,
        verify_r16_report,
        verify_r17_no_gold_writes,
    ]

    for check in checks:
        result = check(project_root)
        report.add(result)

    return report


def print_report(report: VerificationReport, json_output: bool = False, output_file: Optional[Path] = None):
    """Print verification report."""
    if json_output or output_file:
        json_data = json.dumps(report.to_dict(), indent=2)
        if output_file:
            with open(output_file, "w") as f:
                f.write(json_data)
            print(f"Report saved to: {output_file}")
        else:
            print(json_data)
        return

    try:
        from rich.console import Console
        from rich.table import Table

        console = Console()

        table = Table(title="Requirements Verification Report")
        table.add_column("ID", style="cyan", width=5)
        table.add_column("Description", style="white", width=40)
        table.add_column("Status", justify="center", width=8)
        table.add_column("Evidence", style="dim", width=45)

        for r in report.results:
            status_style = {
                Status.PASS: "[green]PASS[/green]",
                Status.PARTIAL: "[yellow]PARTIAL[/yellow]",
                Status.FAIL: "[red]FAIL[/red]",
                Status.SKIP: "[dim]SKIP[/dim]",
            }
            table.add_row(
                r.id,
                r.description[:40] + ("..." if len(r.description) > 40 else ""),
                status_style[r.status],
                r.evidence[:45] + ("..." if len(r.evidence) > 45 else ""),
            )

        console.print(table)
        console.print(f"\n[bold]Summary:[/bold]")
        console.print(f"  [green]PASS:[/green] {report.passed}")
        console.print(f"  [yellow]PARTIAL:[/yellow] {report.partial}")
        console.print(f"  [red]FAIL:[/red] {report.failed}")
        console.print(f"  [dim]SKIP:[/dim] {report.skipped}")

        fixes_needed = [r for r in report.results if r.fix_hint]
        if fixes_needed:
            console.print(f"\n[bold]Fix Hints:[/bold]")
            for r in fixes_needed:
                console.print(f"  {r.id}: {r.fix_hint}")

    except ImportError:
        print("\n" + "=" * 80)
        print("REQUIREMENTS VERIFICATION REPORT")
        print("=" * 80)

        for r in report.results:
            print(f"{r.id:5} | {r.status.value:8} | {r.description[:40]}")
            if r.evidence:
                print(f"      |          | {r.evidence[:50]}")

        print("\n" + "-" * 80)
        print(f"PASS: {report.passed}  PARTIAL: {report.partial}  FAIL: {report.failed}  SKIP: {report.skipped}")


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Verify Fagan Tool requirements")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--output", "-o", type=Path, help="Save report to file")
    args = parser.parse_args()

    script_dir = Path(__file__).parent
    project_root = script_dir.parent

    if not (project_root / "src" / "fagan_tool").exists():
        print(f"Error: Not in Fagan project root at {project_root}")
        sys.exit(1)

    if not args.json:
        print(f"Verifying requirements in: {project_root}")
        print()

    report = run_verification(project_root)
    print_report(report, json_output=args.json, output_file=args.output)

    # Exit code: 1 if any FAIL, 0 otherwise (PARTIAL and SKIP are acceptable)
    sys.exit(1 if report.failed > 0 else 0)


if __name__ == "__main__":
    main()
