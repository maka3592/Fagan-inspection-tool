#!/usr/bin/env python3
"""Calculate metrics from manually validated matches.

This script reads matches_manual.csv (with human annotations) and calculates
TP/FP/FN/Precision/Recall/F1 based on the 'manual_is_true_match' column.

The gold standard file is NOT modified. This provides an alternative evaluation
path for human-validated results.

Usage:
    python scripts/calculate_manual_metrics.py <run_id>
    # or via CLI:
    fagan manual-eval --run <run_id>

Example:
    python scripts/calculate_manual_metrics.py c1_ubr_run_001
"""

import argparse
import csv
import json
import sys
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List


@dataclass
class ManualMetrics:
    """Metrics calculated from manual validation."""
    run_id: str
    timestamp: str

    # Counts
    total_matches: int
    manual_true_positives: int
    manual_false_positives: int
    total_gold: int
    false_negatives: int

    # Rates
    precision: float
    recall: float
    f1_score: float

    # Breakdown by match type
    tp_by_match_type: Dict[str, int]
    fp_by_match_type: Dict[str, int]

    # Notes
    validation_notes: str = ""


def load_manual_matches(manual_path: Path) -> List[Dict]:
    """Load manually validated matches from CSV.

    Args:
        manual_path: Path to matches_manual.csv

    Returns:
        List of match dictionaries
    """
    with open(manual_path, "r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return list(reader)


def load_gold_count(run_id: str) -> int:
    """Load gold defect count from metrics.json.

    Args:
        run_id: Run ID

    Returns:
        Total gold defect count
    """
    metrics_path = Path("eval") / run_id / "metrics.json"
    if metrics_path.exists():
        with open(metrics_path) as f:
            metrics = json.load(f)
        return metrics.get("total_gold", 0)

    # Fallback: try to load gold directly
    try:
        sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
        from fagan_tool.evaluation.gold_loader import GoldLoader

        gold_path = Path("artifacts/gold/Faults_List_In_ver6.xls")
        if gold_path.exists():
            loader = GoldLoader(gold_path)
            defects = loader.load()
            return len(defects)
    except Exception:
        pass

    return 0


def calculate_manual_metrics(run_id: str, eval_dir: Path = None) -> ManualMetrics:
    """Calculate metrics from manually validated matches.

    Args:
        run_id: Run ID
        eval_dir: Optional eval directory

    Returns:
        ManualMetrics object
    """
    if eval_dir is None:
        eval_dir = Path("eval") / run_id

    manual_path = eval_dir / "matches_manual.csv"

    if not manual_path.exists():
        raise FileNotFoundError(
            f"matches_manual.csv not found at {manual_path}. "
            f"Run 'python scripts/create_manual_template.py {run_id}' first."
        )

    matches = load_manual_matches(manual_path)
    total_gold = load_gold_count(run_id)

    # Count TPs and FPs based on manual validation
    manual_tp = 0
    manual_fp = 0
    tp_by_type: Dict[str, int] = {}
    fp_by_type: Dict[str, int] = {}

    for match in matches:
        match_type = match.get("match_type", "UNKNOWN")
        is_tp = match.get("manual_is_true_match", "").upper() == "TRUE"

        if is_tp:
            manual_tp += 1
            tp_by_type[match_type] = tp_by_type.get(match_type, 0) + 1
        else:
            manual_fp += 1
            fp_by_type[match_type] = fp_by_type.get(match_type, 0) + 1

    # Calculate false negatives (gold defects not matched)
    # In manual validation, we trust the human's TP count
    false_negatives = max(0, total_gold - manual_tp)

    # Calculate rates
    precision = manual_tp / (manual_tp + manual_fp) if (manual_tp + manual_fp) > 0 else 0.0
    recall = manual_tp / total_gold if total_gold > 0 else 0.0
    f1_score = (2 * precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0

    return ManualMetrics(
        run_id=run_id,
        timestamp=datetime.utcnow().isoformat(),
        total_matches=len(matches),
        manual_true_positives=manual_tp,
        manual_false_positives=manual_fp,
        total_gold=total_gold,
        false_negatives=false_negatives,
        precision=precision,
        recall=recall,
        f1_score=f1_score,
        tp_by_match_type=tp_by_type,
        fp_by_match_type=fp_by_type,
    )


def save_manual_metrics(metrics: ManualMetrics, eval_dir: Path):
    """Save manual metrics to JSON file.

    Args:
        metrics: ManualMetrics object
        eval_dir: Eval directory
    """
    output_path = eval_dir / "metrics_manual.json"

    with open(output_path, "w") as f:
        json.dump(asdict(metrics), f, indent=2)

    return output_path


def print_metrics(metrics: ManualMetrics):
    """Print metrics to console."""
    try:
        from rich.console import Console
        from rich.table import Table

        console = Console()

        console.print(f"\n[bold]Manual Validation Metrics: {metrics.run_id}[/bold]\n")

        table = Table(show_header=True, header_style="bold cyan")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", justify="right")

        table.add_row("Total Matches Reviewed", str(metrics.total_matches))
        table.add_row("", "")
        table.add_row("Manual True Positives", str(metrics.manual_true_positives))
        table.add_row("Manual False Positives", str(metrics.manual_false_positives))
        table.add_row("Total Gold", str(metrics.total_gold))
        table.add_row("False Negatives", str(metrics.false_negatives))
        table.add_row("", "")
        table.add_row("Precision", f"{metrics.precision:.3f}")
        table.add_row("Recall", f"{metrics.recall:.3f}")
        table.add_row("F1 Score", f"{metrics.f1_score:.3f}")

        console.print(table)

        if metrics.tp_by_match_type:
            console.print("\n[bold]TPs by Match Type:[/bold]")
            for match_type, count in metrics.tp_by_match_type.items():
                console.print(f"  {match_type}: {count}")

        if metrics.fp_by_match_type:
            console.print("\n[bold]FPs by Match Type:[/bold]")
            for match_type, count in metrics.fp_by_match_type.items():
                console.print(f"  {match_type}: {count}")

    except ImportError:
        # Fallback without rich
        print(f"\nManual Validation Metrics: {metrics.run_id}")
        print("=" * 40)
        print(f"Total Matches Reviewed: {metrics.total_matches}")
        print(f"Manual True Positives:  {metrics.manual_true_positives}")
        print(f"Manual False Positives: {metrics.manual_false_positives}")
        print(f"Total Gold:             {metrics.total_gold}")
        print(f"False Negatives:        {metrics.false_negatives}")
        print()
        print(f"Precision: {metrics.precision:.3f}")
        print(f"Recall:    {metrics.recall:.3f}")
        print(f"F1 Score:  {metrics.f1_score:.3f}")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Calculate metrics from manually validated matches"
    )
    parser.add_argument(
        "run_id",
        help="Run ID to calculate metrics for"
    )
    parser.add_argument(
        "--eval-dir",
        type=Path,
        default=None,
        help="Optional eval directory (default: eval/<run_id>)"
    )

    args = parser.parse_args()

    try:
        eval_dir = args.eval_dir or Path("eval") / args.run_id

        metrics = calculate_manual_metrics(args.run_id, eval_dir)
        print_metrics(metrics)

        output_path = save_manual_metrics(metrics, eval_dir)
        print(f"\nMetrics saved to: {output_path}")

    except FileNotFoundError as e:
        print(f"Error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
