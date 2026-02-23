"""Command-line interface for Fagan Inspection Tool."""

import csv
import json
import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
import typer

# Load .env file from current directory or project root
load_dotenv()  # Loads from current directory
load_dotenv(Path(__file__).parent.parent.parent.parent / ".env")  # Project root
import yaml
from rich.console import Console
from rich.table import Table

from .core.process import FaganProcess
from .core.schemas import InspectionConfig, LLMParams
from .evaluation import DefectMatcher, GoldLoader, MetricsCalculator

app = typer.Typer(
    name="fagan",
    help="Multi-Agent LLM-Based Formal Software Inspection Tool (Fagan Process)",
)
console = Console()


@app.command("run")
def run_inspection(
    config_path: Path = typer.Option(
        ...,
        "--config",
        "-c",
        help="Path to inspection configuration file (YAML or JSON)",
    ),
    run_id: Optional[str] = typer.Option(
        None,
        "--run-id",
        "-r",
        help="Override run ID (default: use inspection_id from config)",
    ),
):
    """Run a complete Fagan inspection process."""
    try:
        # Load config
        console.print(f"\n[cyan]Loading configuration from {config_path}[/cyan]")
        config = load_config(config_path)

        # Run inspection
        process = FaganProcess(config, run_id_override=run_id)
        run = process.run()

        console.print(f"\n[bold green]✓ Inspection completed successfully![/bold green]")
        console.print(f"Run ID: {run.metadata.inspection_id}")
        console.print(f"Total defects found: {len(run.final_defects)}")
        console.print(f"Results: runs/{run.metadata.inspection_id}/")

    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        raise typer.Exit(1)


@app.command("eval")
def evaluate_run(
    run_id: str = typer.Option(..., "--run", "-r", help="Run ID to evaluate"),
    gold_path: Path = typer.Option(
        Path("artifacts/gold/Faults_List_In_ver6.xls"),
        "--gold",
        "-g",
        help="Path to gold standard file",
    ),
    output_dir: Optional[Path] = typer.Option(
        None,
        "--output",
        "-o",
        help="Output directory (default: eval/)",
    ),
    threshold_recall: Optional[float] = typer.Option(
        None,
        "--threshold-recall",
        "-tr",
        help="Minimum recall threshold for pass (0.0-1.0)",
        min=0.0,
        max=1.0,
    ),
    threshold_precision: Optional[float] = typer.Option(
        None,
        "--threshold-precision",
        "-tp",
        help="Minimum precision threshold for pass (0.0-1.0)",
        min=0.0,
        max=1.0,
    ),
    threshold_f1: Optional[float] = typer.Option(
        None,
        "--threshold-f1",
        "-tf",
        help="Minimum F1 score threshold for pass (0.0-1.0)",
        min=0.0,
        max=1.0,
    ),
    threshold_recall_a: Optional[float] = typer.Option(
        None,
        "--threshold-recall-a",
        "-tra",
        help="Minimum recall for high-risk (A) defects (0.0-1.0)",
        min=0.0,
        max=1.0,
    ),
    fail_on_threshold: bool = typer.Option(
        False,
        "--fail-on-threshold",
        "-f",
        help="Exit with code 1 if any threshold is not met",
    ),
    match_threshold: float = typer.Option(
        0.60,
        "--match-threshold",
        "-mt",
        help="Similarity threshold for partial match (0.0-1.0). Default: 0.60",
        min=0.0,
        max=1.0,
    ),
    gold_aligned: bool = typer.Option(
        False,
        "--gold-aligned",
        help="Evaluate using final_defects_gold_aligned.json (filtered subset) instead of all defects.",
    ),
    defects_file: Optional[Path] = typer.Option(
        None,
        "--defects-file",
        help="Path to a specific defects JSON file to evaluate (overrides --gold-aligned).",
    ),
):
    """Evaluate inspection results against gold standard.

    Supports optional thresholds for pass/fail determination:

        fagan eval --run my_run --threshold-recall 0.5 --threshold-f1 0.4

    Use --match-threshold to control similarity cutoff for partial matches
    (default: 0.60, recommended after signal-gate improvements: 0.70):

        fagan eval --run my_run --match-threshold 0.70

    Use --gold-aligned to evaluate only the gold-aligned subset (fewer FP
    from novel defects not in gold):

        fagan eval --run my_run --gold-aligned

    Use --defects-file to evaluate an arbitrary defects JSON file:

        fagan eval --run my_run --defects-file runs/my_run/custom.json

    Use --fail-on-threshold to exit with code 1 if thresholds are not met.
    """
    try:
        console.print(f"\n[cyan]Evaluating run: {run_id}[/cyan]")

        # Load run results
        run_dir = Path("runs") / run_id
        if not run_dir.exists():
            console.print(f"[red]Run directory not found: {run_dir}[/red]")
            raise typer.Exit(1)

        # Determine which defects file to load
        if defects_file is not None:
            defects_path = defects_file
        elif gold_aligned:
            defects_path = run_dir / "final_defects_gold_aligned.json"
        else:
            defects_path = run_dir / "final_defects.json"

        defects_file_name = defects_path.name if isinstance(defects_path, Path) else str(defects_path)

        if not Path(defects_path).exists():
            console.print(f"[red]Defects file not found: {defects_path}[/red]")
            if gold_aligned:
                console.print("[yellow]Hint: re-run 'fagan run' to generate the gold-aligned file.[/yellow]")
            raise typer.Exit(1)

        console.print(f"Loading defects from {defects_path}")
        with open(defects_path) as f:
            defects_data = json.load(f)

        from .core.schemas import Defect, EvaluationMetadata, EvaluationThresholds

        found_defects = [Defect(**d) for d in defects_data]

        # Load gold standard
        console.print(f"Loading gold standard from {gold_path}")
        gold_loader = GoldLoader(gold_path)
        gold_defects = gold_loader.load()
        console.print(f"  Gold defects: {len(gold_defects)}")

        # Match defects with configurable threshold
        console.print(f"Matching defects (threshold: {match_threshold:.2f})...")
        matcher = DefectMatcher(description_threshold=match_threshold)
        # Pass eval output dir for match debug (enabled by FAGAN_MATCH_DEBUG=1)
        eval_debug_dir = (Path("eval") / run_id) if output_dir is None else output_dir
        matches, stats = matcher.match(found_defects, gold_defects, debug_output_dir=eval_debug_dir)

        # Calculate metrics
        console.print("Calculating metrics...")
        metrics = MetricsCalculator.calculate(
            run_id, found_defects, gold_defects, matches, stats,
            match_threshold=match_threshold
        )

        # Build thresholds if any specified
        has_thresholds = any([
            threshold_recall is not None,
            threshold_precision is not None,
            threshold_f1 is not None,
            threshold_recall_a is not None,
        ])

        if has_thresholds:
            thresholds = EvaluationThresholds(
                min_recall=threshold_recall,
                min_precision=threshold_precision,
                min_f1=threshold_f1,
                min_recall_risk_a=threshold_recall_a,
            )
            metrics.thresholds = thresholds

            # Evaluate against thresholds
            threshold_results = {}
            all_passed = True

            if threshold_recall is not None:
                passed = metrics.recall >= threshold_recall
                threshold_results["recall"] = passed
                if not passed:
                    all_passed = False

            if threshold_precision is not None:
                passed = metrics.precision >= threshold_precision
                threshold_results["precision"] = passed
                if not passed:
                    all_passed = False

            if threshold_f1 is not None:
                passed = metrics.f1_score >= threshold_f1
                threshold_results["f1_score"] = passed
                if not passed:
                    all_passed = False

            if threshold_recall_a is not None:
                recall_a = metrics.recall_by_risk.get("A", 0.0)
                passed = recall_a >= threshold_recall_a
                threshold_results["recall_risk_a"] = passed
                if not passed:
                    all_passed = False

            metrics.threshold_results = threshold_results
            metrics.passed = all_passed

        # Add evaluation metadata with match_threshold
        metrics.evaluation_metadata = EvaluationMetadata(
            gold_standard_path=str(gold_path),
            gold_defect_count=len(gold_defects),
            matcher_thresholds={
                "match_threshold": match_threshold,
                "description_threshold": matcher.description_threshold,
                "exact_threshold": matcher.exact_threshold,
                "position_threshold": matcher.position_threshold,
            },
            evaluation_version="1.3.0",
            defects_file_used=defects_file_name,
        )

        # Save results
        if output_dir is None:
            output_dir = Path("eval") / run_id
        output_dir.mkdir(parents=True, exist_ok=True)

        # Save matches
        matches_path = output_dir / "matches.json"
        with open(matches_path, "w") as f:
            json.dump(
                [m.model_dump(mode="json") for m in matches],
                f,
                indent=2,
            )

        # Save metrics
        metrics_path = output_dir / "metrics.json"
        with open(metrics_path, "w") as f:
            json.dump(metrics.model_dump(mode="json"), f, indent=2, default=str)

        # Export matches to CSV
        csv_path = output_dir / "matches_enriched.csv"
        export_matches_to_csv(matches, found_defects, gold_defects, csv_path)

        # Display metrics
        display_metrics(metrics)

        console.print(f"\n[green]Results saved to {output_dir}/[/green]")
        console.print(f"  - matches.json")
        console.print(f"  - matches_enriched.csv")
        console.print(f"  - metrics.json")

        # Exit with error if thresholds not met and --fail-on-threshold is set
        if fail_on_threshold and has_thresholds and not metrics.passed:
            console.print(f"\n[bold red]Evaluation FAILED: thresholds not met[/bold red]")
            raise typer.Exit(1)

    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        import traceback

        traceback.print_exc()
        raise typer.Exit(1)


@app.command("report")
def build_report(
    run_id: str = typer.Option(..., "--run", "-r", help="Run ID for report"),
    output: Optional[Path] = typer.Option(
        None,
        "--output",
        "-o",
        help="Output path for report (default: eval/<run_id>/report.md)",
    ),
):
    """Build evaluation report from run results."""
    try:
        console.print(f"\n[cyan]Building report for run: {run_id}[/cyan]")

        # Load metrics
        eval_dir = Path("eval") / run_id
        metrics_path = eval_dir / "metrics.json"

        if not metrics_path.exists():
            console.print(
                f"[red]Metrics not found. Run 'fagan eval --run {run_id}' first.[/red]"
            )
            raise typer.Exit(1)

        with open(metrics_path) as f:
            metrics_data = json.load(f)

        from .core.schemas import EvaluationMetrics

        metrics = EvaluationMetrics(**metrics_data)

        # Generate report
        report = generate_markdown_report(run_id, metrics)

        # Save report
        if output is None:
            output = eval_dir / "report.md"

        with open(output, "w") as f:
            f.write(report)

        console.print(f"[green]Report saved to {output}[/green]")

    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        raise typer.Exit(1)


@app.command("dry-run")
def dry_run():
    """Run inspection in dry-run mode (no API calls, deterministic output)."""
    try:
        console.print("\n[cyan]Running dry-run inspection...[/cyan]")
        console.print("[yellow]Note: This mode generates simulated outputs without API calls[/yellow]\n")

        # Create minimal dry-run config
        from .core.schemas import ConditionType, ReadingTechnique

        config = InspectionConfig(
            inspection_id="demo_dry_run",
            condition=ConditionType.C1_UBR,
            reading_techniques=[ReadingTechnique.UBR],
            artifacts=["design/example.pdf"],  # Will not actually be loaded
            llm_params=LLMParams(
                model="dry-run",
                provider="none",
            ),
            dry_run=True,
        )

        # Run
        process = FaganProcess(config)
        run = process.run()

        console.print(f"\n[bold green]✓ Dry-run completed![/bold green]")
        console.print(f"Generated {len(run.final_defects)} simulated defects")
        console.print(f"Results: runs/{run.metadata.inspection_id}/")

    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        raise typer.Exit(1)


def load_config(config_path: Path) -> InspectionConfig:
    """Load inspection configuration from file.

    Args:
        config_path: Path to config file

    Returns:
        InspectionConfig object
    """
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with open(config_path) as f:
        if config_path.suffix in [".yaml", ".yml"]:
            data = yaml.safe_load(f)
        else:
            data = json.load(f)

    # Parse into InspectionConfig
    from .core.schemas import ConditionType, LLMParams, ReadingTechnique

    config = InspectionConfig(
        inspection_id=data["inspection_id"],
        condition=ConditionType(data["condition"]),
        reading_techniques=[ReadingTechnique(t) for t in data["reading_techniques"]],
        artifacts=data["artifacts"],
        llm_params=LLMParams(**data["llm_params"]),
        prompt_versions=data.get("prompt_versions", {}),
        dry_run=data.get("dry_run", False),
        extra_config=data.get("extra_config", {}),
    )

    return config


def display_metrics(metrics):
    """Display metrics in a formatted table.

    Args:
        metrics: EvaluationMetrics object
    """
    console.print("\n[bold]Evaluation Metrics:[/bold]\n")

    # Main metrics table
    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", justify="right")

    table.add_row("Match Threshold", f"{metrics.match_threshold:.2f}")
    table.add_row("", "")
    table.add_row("Total Found", str(metrics.total_found))
    table.add_row("Total Gold", str(metrics.total_gold))
    table.add_row("True Positives", str(metrics.true_positives))
    table.add_row("  - Exact (>= 0.85)", str(metrics.true_positives_exact))
    table.add_row("  - Partial (< 0.85)", str(metrics.true_positives_partial))
    table.add_row("False Positives (Total)", str(metrics.false_positives))
    table.add_row("  - In-scope FP", str(metrics.false_positives_in_scope))
    table.add_row("  - Out-of-scope FP", str(metrics.false_positives_out_of_scope))
    table.add_row("False Negatives", str(metrics.false_negatives))
    table.add_row("Duplicates", str(metrics.duplicates))
    table.add_row("", "")
    table.add_row("Precision (Overall)", f"{metrics.precision:.3f}")
    table.add_row("Precision (In-scope)", f"{metrics.precision_in_scope:.3f}")
    table.add_row("Recall", f"{metrics.recall:.3f}")
    table.add_row("F1 Score", f"{metrics.f1_score:.3f}")
    table.add_row("", "")
    table.add_row("TP Similarity Mean", f"{metrics.similarity_score_mean_tp:.3f}")
    table.add_row("TP Similarity Min", f"{metrics.similarity_score_min_tp:.3f}")
    table.add_row("TP Similarity Max", f"{metrics.similarity_score_max_tp:.3f}")

    console.print(table)

    # Recall by risk
    console.print("\n[bold]Recall by Risk Level:[/bold]\n")
    risk_table = Table(show_header=True, header_style="bold cyan")
    risk_table.add_column("Risk Level", style="cyan")
    risk_table.add_column("Recall", justify="right")

    for risk, recall in metrics.recall_by_risk.items():
        risk_table.add_row(risk, f"{recall:.3f}")

    console.print(risk_table)

    # Display threshold results if present
    if metrics.thresholds is not None:
        console.print("\n[bold]Threshold Evaluation:[/bold]\n")
        threshold_table = Table(show_header=True, header_style="bold cyan")
        threshold_table.add_column("Metric", style="cyan")
        threshold_table.add_column("Actual", justify="right")
        threshold_table.add_column("Threshold", justify="right")
        threshold_table.add_column("Status", justify="center")

        def status_str(passed: bool) -> str:
            return "[green]PASS[/green]" if passed else "[red]FAIL[/red]"

        if metrics.thresholds.min_recall is not None:
            passed = metrics.threshold_results.get("recall", False)
            threshold_table.add_row(
                "Recall",
                f"{metrics.recall:.3f}",
                f">= {metrics.thresholds.min_recall:.3f}",
                status_str(passed),
            )

        if metrics.thresholds.min_precision is not None:
            passed = metrics.threshold_results.get("precision", False)
            threshold_table.add_row(
                "Precision",
                f"{metrics.precision:.3f}",
                f">= {metrics.thresholds.min_precision:.3f}",
                status_str(passed),
            )

        if metrics.thresholds.min_f1 is not None:
            passed = metrics.threshold_results.get("f1_score", False)
            threshold_table.add_row(
                "F1 Score",
                f"{metrics.f1_score:.3f}",
                f">= {metrics.thresholds.min_f1:.3f}",
                status_str(passed),
            )

        if metrics.thresholds.min_recall_risk_a is not None:
            recall_a = metrics.recall_by_risk.get("A", 0.0)
            passed = metrics.threshold_results.get("recall_risk_a", False)
            threshold_table.add_row(
                "Recall (Risk A)",
                f"{recall_a:.3f}",
                f">= {metrics.thresholds.min_recall_risk_a:.3f}",
                status_str(passed),
            )

        console.print(threshold_table)

        # Overall pass/fail
        if metrics.passed is not None:
            if metrics.passed:
                console.print("\n[bold green]Overall Result: PASS[/bold green]")
            else:
                console.print("\n[bold red]Overall Result: FAIL[/bold red]")


def generate_markdown_report(run_id: str, metrics) -> str:
    """Generate markdown report.

    Args:
        run_id: Run identifier
        metrics: EvaluationMetrics object

    Returns:
        Markdown report string
    """
    # Determine overall status
    status_badge = ""
    if metrics.passed is not None:
        if metrics.passed:
            status_badge = "**Status:** PASS"
        else:
            status_badge = "**Status:** FAIL"

    report = f"""# Fagan Inspection Evaluation Report

**Run ID:** {run_id}
**Date:** {metrics.timestamp}
{status_badge}

## Summary

- **Match Threshold:** {metrics.match_threshold:.2f}
- **Total Defects Found:** {metrics.total_found}
- **Total Gold Standard Defects:** {metrics.total_gold}
- **True Positives:** {metrics.true_positives}
  - Exact (similarity >= 0.85): {metrics.true_positives_exact}
  - Partial (threshold <= similarity < 0.85): {metrics.true_positives_partial}
- **False Positives (Total):** {metrics.false_positives}
  - In-scope FP: {metrics.false_positives_in_scope}
  - Out-of-scope FP: {metrics.false_positives_out_of_scope}
- **False Negatives:** {metrics.false_negatives}
- **Duplicates:** {metrics.duplicates}

## Performance Metrics

| Metric | Value |
|--------|-------|
| Precision (Overall) | {metrics.precision:.3f} |
| Precision (In-scope) | {metrics.precision_in_scope:.3f} |
| Recall | {metrics.recall:.3f} |
| F1 Score | {metrics.f1_score:.3f} |

## True Positive Similarity Statistics

| Metric | Value |
|--------|-------|
| TP Similarity Mean | {metrics.similarity_score_mean_tp:.3f} |
| TP Similarity Min | {metrics.similarity_score_min_tp:.3f} |
| TP Similarity Max | {metrics.similarity_score_max_tp:.3f} |

## Recall by Risk Level

| Risk Level | Recall |
|------------|--------|
"""

    for risk, recall in metrics.recall_by_risk.items():
        report += f"| {risk} | {recall:.3f} |\n"

    # Add threshold evaluation section if thresholds were used
    if metrics.thresholds is not None:
        report += """
## Threshold Evaluation

| Metric | Actual | Threshold | Status |
|--------|--------|-----------|--------|
"""
        if metrics.thresholds.min_recall is not None:
            passed = metrics.threshold_results.get("recall", False)
            status = "PASS" if passed else "FAIL"
            report += f"| Recall | {metrics.recall:.3f} | >= {metrics.thresholds.min_recall:.3f} | {status} |\n"

        if metrics.thresholds.min_precision is not None:
            passed = metrics.threshold_results.get("precision", False)
            status = "PASS" if passed else "FAIL"
            report += f"| Precision | {metrics.precision:.3f} | >= {metrics.thresholds.min_precision:.3f} | {status} |\n"

        if metrics.thresholds.min_f1 is not None:
            passed = metrics.threshold_results.get("f1_score", False)
            status = "PASS" if passed else "FAIL"
            report += f"| F1 Score | {metrics.f1_score:.3f} | >= {metrics.thresholds.min_f1:.3f} | {status} |\n"

        if metrics.thresholds.min_recall_risk_a is not None:
            recall_a = metrics.recall_by_risk.get("A", 0.0)
            passed = metrics.threshold_results.get("recall_risk_a", False)
            status = "PASS" if passed else "FAIL"
            report += f"| Recall (Risk A) | {recall_a:.3f} | >= {metrics.thresholds.min_recall_risk_a:.3f} | {status} |\n"

        overall = "PASS" if metrics.passed else "FAIL"
        report += f"\n**Overall Result:** {overall}\n"

    report += f"""
## Additional Statistics

- **Average Findings per Reviewer:** {metrics.avg_findings_per_reviewer:.1f}

## Interpretation

- **Precision (Overall) ({metrics.precision:.1%})**: Of all defects reported, {metrics.precision:.1%} were genuine.
- **Precision (In-scope) ({metrics.precision_in_scope:.1%})**: Excludes out-of-scope defects (e.g., Use Cases not in gold standard).
- **Recall ({metrics.recall:.1%})**: The inspection detected {metrics.recall:.1%} of known defects.
- **F1 Score ({metrics.f1_score:.3f})**: Harmonic mean of precision and recall.

## False Positive Analysis

**In-scope False Positives ({metrics.false_positives_in_scope})**: Defects within gold standard scope (Design/MSC sections) that were not found in gold standard. These may represent genuine issues not in the gold set or actual false alarms.

**Out-of-scope False Positives ({metrics.false_positives_out_of_scope})**: Defects in areas not covered by gold standard (e.g., Use Case sections). Gold standard focuses on Design/MSC sections only, so these are expected and excluded from in-scope precision calculation.
"""

    # Add evaluation metadata section if present
    if metrics.evaluation_metadata is not None:
        report += f"""
## Evaluation Metadata

- **Gold Standard File:** {metrics.evaluation_metadata.gold_standard_path}
- **Gold Defect Count:** {metrics.evaluation_metadata.gold_defect_count}
- **Evaluation Version:** {metrics.evaluation_metadata.evaluation_version}
- **Matcher Thresholds:**
"""
        for key, value in metrics.evaluation_metadata.matcher_thresholds.items():
            report += f"  - {key}: {value}\n"

    report += """
---

*Generated by Fagan Inspection Tool*
"""

    return report


def export_matches_to_csv(matches, found_defects, gold_defects, csv_path: Path):
    """Export matches to CSV with enriched defect details.

    Args:
        matches: List of DefectMatch objects
        found_defects: List of found Defect objects
        gold_defects: List of GoldDefect objects
        csv_path: Path to save CSV file
    """
    # Create lookup dictionaries
    found_lookup = {d.id: d for d in found_defects}
    gold_lookup = {g.id: g for g in gold_defects}

    # Prepare CSV rows
    rows = []
    for match in matches:
        row = {
            "match_type": match.match_type.value,
            "similarity_score": f"{match.similarity_score:.3f}",
            "notes": match.notes,
            "found_id": match.found_id,
            "found_position": "",
            "found_risk": "",
            "found_fault_type": "",
            "found_description": "",
            "found_page_hint": "",
            "gold_id": match.gold_id or "",
            "gold_position": "",
            "gold_risk": "",
            "gold_fault_type": "",
            "gold_description": "",
        }

        # Add found defect details
        if match.found_id in found_lookup:
            found = found_lookup[match.found_id]
            row["found_position"] = found.position
            row["found_risk"] = found.risk.value
            row["found_fault_type"] = found.fault_type.value
            row["found_description"] = found.description[:100] + ("..." if len(found.description) > 100 else "")
            row["found_page_hint"] = found.page_hint or ""

        # Add gold defect details
        if match.gold_id and match.gold_id in gold_lookup:
            gold = gold_lookup[match.gold_id]
            row["gold_position"] = gold.position
            row["gold_risk"] = gold.risk.value
            row["gold_fault_type"] = gold.fault_type.value
            row["gold_description"] = gold.description[:100] + ("..." if len(gold.description) > 100 else "")

        # Add debug fields
        row["best_candidate_gold_id"] = match.best_candidate_gold_id or ""
        row["best_candidate_gold_position"] = match.best_candidate_gold_position or ""
        row["best_candidate_similarity"] = f"{match.best_candidate_similarity:.3f}"
        row["best_candidate_match_reason"] = match.best_candidate_match_reason

        rows.append(row)

    # Write CSV
    if rows:
        fieldnames = [
            "match_type", "similarity_score", "notes",
            "found_id", "found_position", "found_risk", "found_fault_type",
            "found_description", "found_page_hint",
            "gold_id", "gold_position", "gold_risk", "gold_fault_type",
            "gold_description",
            "best_candidate_gold_id", "best_candidate_gold_position",
            "best_candidate_similarity", "best_candidate_match_reason",
        ]

        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)


@app.command("verify")
def verify_requirements():
    """Verify all professor requirements for the Fagan Inspection Tool.

    Runs automated checks on all requirements from REQUIREMENTS_CHECKLIST.md
    and produces a PASS/PARTIAL/FAIL report.
    """
    import sys
    from pathlib import Path

    # Find project root (where pyproject.toml is)
    script_dir = Path(__file__).parent
    project_root = script_dir.parent.parent.parent

    # Import and run verification
    sys.path.insert(0, str(project_root / "scripts"))

    try:
        from verify_requirements import run_verification, print_report

        console.print("\n[cyan]Verifying professor requirements...[/cyan]\n")

        report = run_verification(project_root)
        print_report(report)

        if report.failed > 0:
            raise typer.Exit(1)

    except ImportError as e:
        console.print(f"[red]Error importing verification script: {e}[/red]")
        console.print("Run directly: python scripts/verify_requirements.py")
        raise typer.Exit(1)


@app.command("manual-template")
def create_manual_template(
    run_id: str = typer.Option(..., "--run", "-r", help="Run ID to create template for"),
    output_dir: Optional[Path] = typer.Option(
        None,
        "--output",
        "-o",
        help="Output directory (default: eval/<run_id>)",
    ),
):
    """Create manual validation template from matches_enriched.csv.

    Copies matches_enriched.csv to matches_manual.csv and adds a
    'manual_is_true_match' column (default: FALSE) for human annotation.

    Example:
        fagan manual-template --run c1_ubr_run_001
    """
    try:
        if output_dir is None:
            output_dir = Path("eval") / run_id

        enriched_path = output_dir / "matches_enriched.csv"
        manual_path = output_dir / "matches_manual.csv"

        if not enriched_path.exists():
            console.print(f"[red]Error: {enriched_path} not found[/red]")
            console.print(f"Run 'fagan eval --run {run_id}' first.")
            raise typer.Exit(1)

        # Read enriched CSV
        with open(enriched_path, "r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            fieldnames = list(reader.fieldnames) if reader.fieldnames else []

        # Add manual validation columns
        new_fieldnames = fieldnames + ["manual_is_true_match", "manual_notes"]

        for row in rows:
            row["manual_is_true_match"] = "FALSE"
            row["manual_notes"] = ""

        # Write manual template
        with open(manual_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=new_fieldnames)
            writer.writeheader()
            writer.writerows(rows)

        console.print(f"[green]Manual validation template created: {manual_path}[/green]")
        console.print()
        console.print("[bold]Instructions:[/bold]")
        console.print("1. Open the CSV file in a spreadsheet editor")
        console.print("2. Review each match and set 'manual_is_true_match' to TRUE if correct")
        console.print("3. Add notes in 'manual_notes' column if needed")
        console.print("4. Save the file")
        console.print(f"5. Run: fagan manual-eval --run {run_id}")

    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        raise typer.Exit(1)


@app.command("manual-eval")
def calculate_manual_metrics(
    run_id: str = typer.Option(..., "--run", "-r", help="Run ID to evaluate"),
    output_dir: Optional[Path] = typer.Option(
        None,
        "--output",
        "-o",
        help="Output directory (default: eval/<run_id>)",
    ),
):
    """Calculate metrics from manually validated matches.

    Reads matches_manual.csv (with human annotations) and calculates
    TP/FP/FN/Precision/Recall/F1 based on the 'manual_is_true_match' column.

    The gold standard file is NOT modified.

    Example:
        fagan manual-eval --run c1_ubr_run_001
    """
    from datetime import datetime

    try:
        if output_dir is None:
            output_dir = Path("eval") / run_id

        manual_path = output_dir / "matches_manual.csv"

        if not manual_path.exists():
            console.print(f"[red]Error: {manual_path} not found[/red]")
            console.print(f"Run 'fagan manual-template --run {run_id}' first.")
            raise typer.Exit(1)

        # Load manual matches
        with open(manual_path, "r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            matches = list(reader)

        # Load gold count from metrics.json
        metrics_path = output_dir / "metrics.json"
        total_gold = 0
        if metrics_path.exists():
            with open(metrics_path) as f:
                auto_metrics = json.load(f)
            total_gold = auto_metrics.get("total_gold", 0)

        # Count TPs and FPs based on manual validation
        manual_tp = 0
        manual_fp = 0
        tp_by_type = {}
        fp_by_type = {}

        for match in matches:
            match_type = match.get("match_type", "UNKNOWN")
            is_tp = match.get("manual_is_true_match", "").upper() == "TRUE"

            if is_tp:
                manual_tp += 1
                tp_by_type[match_type] = tp_by_type.get(match_type, 0) + 1
            else:
                manual_fp += 1
                fp_by_type[match_type] = fp_by_type.get(match_type, 0) + 1

        # Calculate metrics
        false_negatives = max(0, total_gold - manual_tp)
        precision = manual_tp / (manual_tp + manual_fp) if (manual_tp + manual_fp) > 0 else 0.0
        recall = manual_tp / total_gold if total_gold > 0 else 0.0
        f1_score = (2 * precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0

        # Display results
        console.print(f"\n[bold]Manual Validation Metrics: {run_id}[/bold]\n")

        table = Table(show_header=True, header_style="bold cyan")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", justify="right")

        table.add_row("Total Matches Reviewed", str(len(matches)))
        table.add_row("", "")
        table.add_row("Manual True Positives", str(manual_tp))
        table.add_row("Manual False Positives", str(manual_fp))
        table.add_row("Total Gold", str(total_gold))
        table.add_row("False Negatives", str(false_negatives))
        table.add_row("", "")
        table.add_row("Precision", f"{precision:.3f}")
        table.add_row("Recall", f"{recall:.3f}")
        table.add_row("F1 Score", f"{f1_score:.3f}")

        console.print(table)

        # Save to JSON
        manual_metrics = {
            "run_id": run_id,
            "timestamp": datetime.utcnow().isoformat(),
            "total_matches": len(matches),
            "manual_true_positives": manual_tp,
            "manual_false_positives": manual_fp,
            "total_gold": total_gold,
            "false_negatives": false_negatives,
            "precision": precision,
            "recall": recall,
            "f1_score": f1_score,
            "tp_by_match_type": tp_by_type,
            "fp_by_match_type": fp_by_type,
        }

        output_path = output_dir / "metrics_manual.json"
        with open(output_path, "w") as f:
            json.dump(manual_metrics, f, indent=2)

        console.print(f"\n[green]Metrics saved to: {output_path}[/green]")

    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        import traceback
        traceback.print_exc()
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
