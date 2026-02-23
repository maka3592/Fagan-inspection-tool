#!/usr/bin/env python3
"""Create a manual validation template from matches_enriched.csv.

This script copies matches_enriched.csv to matches_manual.csv and adds
a 'manual_is_true_match' column (default: FALSE) for human annotation.

Usage:
    python scripts/create_manual_template.py <run_id>
    # or via CLI:
    fagan manual-template --run <run_id>

Example:
    python scripts/create_manual_template.py c1_ubr_run_001
"""

import argparse
import csv
import sys
from pathlib import Path


def create_manual_template(run_id: str, eval_dir: Path = None) -> Path:
    """Create manual validation template from enriched matches.

    Args:
        run_id: Run ID to create template for
        eval_dir: Optional eval directory (default: eval/<run_id>)

    Returns:
        Path to created template file

    Raises:
        FileNotFoundError: If matches_enriched.csv doesn't exist
    """
    if eval_dir is None:
        eval_dir = Path("eval") / run_id

    enriched_path = eval_dir / "matches_enriched.csv"
    manual_path = eval_dir / "matches_manual.csv"

    if not enriched_path.exists():
        raise FileNotFoundError(
            f"matches_enriched.csv not found at {enriched_path}. "
            f"Run 'fagan eval --run {run_id}' first."
        )

    # Read enriched CSV
    with open(enriched_path, "r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        fieldnames = reader.fieldnames

    if not rows:
        print(f"Warning: No matches found in {enriched_path}")

    # Add manual validation column
    new_fieldnames = list(fieldnames) + ["manual_is_true_match", "manual_notes"]

    for row in rows:
        # Default to FALSE - human must explicitly mark TRUE
        row["manual_is_true_match"] = "FALSE"
        row["manual_notes"] = ""

    # Write manual template
    with open(manual_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=new_fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    return manual_path


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Create manual validation template from matches_enriched.csv"
    )
    parser.add_argument(
        "run_id",
        help="Run ID to create template for"
    )
    parser.add_argument(
        "--eval-dir",
        type=Path,
        default=None,
        help="Optional eval directory (default: eval/<run_id>)"
    )

    args = parser.parse_args()

    try:
        output_path = create_manual_template(args.run_id, args.eval_dir)
        print(f"Manual validation template created: {output_path}")
        print()
        print("Instructions:")
        print("1. Open the CSV file in a spreadsheet editor")
        print("2. Review each match and set 'manual_is_true_match' to TRUE if correct")
        print("3. Add notes in 'manual_notes' column if needed")
        print("4. Save the file")
        print(f"5. Run: python scripts/calculate_manual_metrics.py {args.run_id}")

    except FileNotFoundError as e:
        print(f"Error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
