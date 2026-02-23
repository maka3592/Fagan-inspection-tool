#!/usr/bin/env python3
"""Enrich matches.json with gold and found defect details."""

import json
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from fagan_tool.evaluation.gold_loader import GoldLoader
from fagan_tool.core.schemas import Defect


def enrich_matches(run_id: str, gold_path: Path):
    """Enrich matches with defect details.

    Args:
        run_id: Run ID to enrich
        gold_path: Path to gold standard Excel file
    """
    eval_dir = Path("eval") / run_id
    run_dir = Path("runs") / run_id

    # Load matches
    matches_path = eval_dir / "matches.json"
    with open(matches_path) as f:
        matches = json.load(f)

    # Load found defects
    defects_path = run_dir / "final_defects.json"
    with open(defects_path) as f:
        defects_data = json.load(f)
    found_defects = [Defect(**d) for d in defects_data]
    found_lookup = {d.id: d for d in found_defects}

    # Load gold defects
    gold_loader = GoldLoader(gold_path)
    gold_defects = gold_loader.load()
    gold_lookup = {g.id: g for g in gold_defects}

    print(f"Loaded {len(matches)} matches")
    print(f"Loaded {len(found_defects)} found defects")
    print(f"Loaded {len(gold_defects)} gold defects")

    # Enrich matches
    enriched = []
    for match in matches:
        enriched_match = match.copy()

        # Add found defect details
        found_id = match["found_id"]
        if found_id in found_lookup:
            found = found_lookup[found_id]
            enriched_match["found_position"] = found.position
            enriched_match["found_risk"] = found.risk.value
            enriched_match["found_fault_type"] = found.fault_type.value
            enriched_match["found_description"] = found.description
            enriched_match["found_page_hint"] = found.page_hint if hasattr(found, 'page_hint') else None

        # Add gold defect details
        gold_id = match["gold_id"]
        if gold_id and gold_id in gold_lookup:
            gold = gold_lookup[gold_id]
            enriched_match["gold_position"] = gold.position
            enriched_match["gold_risk"] = gold.risk.value
            enriched_match["gold_fault_type"] = gold.fault_type.value
            enriched_match["gold_description"] = gold.description
        else:
            enriched_match["gold_position"] = None
            enriched_match["gold_risk"] = None
            enriched_match["gold_fault_type"] = None
            enriched_match["gold_description"] = None

        enriched.append(enriched_match)

    # Save enriched JSON
    enriched_json_path = eval_dir / "matches_enriched.json"
    with open(enriched_json_path, "w") as f:
        json.dump(enriched, f, indent=2)

    # Save enriched CSV
    import csv
    enriched_csv_path = eval_dir / "matches_enriched.csv"
    if enriched:
        fieldnames = [
            "match_type", "similarity_score", "notes",
            "found_id", "found_position", "found_risk", "found_fault_type", "found_description", "found_page_hint",
            "gold_id", "gold_position", "gold_risk", "gold_fault_type", "gold_description"
        ]
        with open(enriched_csv_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(enriched)

    print(f"\nEnriched matches saved to:")
    print(f"  - {enriched_json_path}")
    print(f"  - {enriched_csv_path}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Enrich matches with defect details")
    parser.add_argument("run_id", help="Run ID to enrich")
    parser.add_argument(
        "--gold",
        default="artifacts/gold/Faults_List_In_ver6.xlsx",
        help="Path to gold standard Excel file"
    )

    args = parser.parse_args()

    enrich_matches(args.run_id, Path(args.gold))
