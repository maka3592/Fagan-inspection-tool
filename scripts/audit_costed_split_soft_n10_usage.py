#!/usr/bin/env python3
"""Usage-/Kosten-Audit für den Datensatz ``costed_split_soft_n10``.

Prüft alle im Manifest geplanten 40 Runs auf ihre
``runs/<run_id>/llm_usage.csv`` und erzeugt:

- ``results/costed_split_soft_n10_usage_summary.csv``     (pro Run)
- ``results/costed_split_soft_n10_usage_by_technique.csv``(aggregiert je Technik)

Kosten sind listenpreisbasierte API-Kosten (USD) auf Basis realer,
gemessener Tokenusage (siehe configs/llm_costs.yaml). Goldstandard und
Evaluation-Code werden nicht berührt.
"""

from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path
from typing import Dict, List

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
MANIFEST = _PROJECT_ROOT / "results" / "costed_split_soft_n10_manifest.csv"
RUNS_DIR = _PROJECT_ROOT / "runs"
SUMMARY_OUT = _PROJECT_ROOT / "results" / "costed_split_soft_n10_usage_summary.csv"
BY_TECH_OUT = _PROJECT_ROOT / "results" / "costed_split_soft_n10_usage_by_technique.csv"

DATASET = "costed_split_soft_n10"
REVIEWER_PHASE = "individual_inspection"
COST_CRITICAL = ["input_tokens", "output_tokens", "total_tokens",
                 "duration_seconds", "total_cost", "run_id", "technique",
                 "phase", "agent_role"]

SUMMARY_COLS = [
    "dataset", "run_id", "technique", "usage_file_exists", "row_count",
    "reviewer_call_count", "reviewer_id_filled_for_reviewer_calls",
    "usage_available_true_count", "input_tokens_total", "output_tokens_total",
    "total_tokens_total", "total_cost_usd", "duration_seconds_total",
    "usable_for_cost_analysis", "notes",
]
BY_TECH_COLS = [
    "dataset", "technique", "runs_completed", "calls_total",
    "reviewer_calls_total", "input_tokens_total", "output_tokens_total",
    "total_tokens_total", "total_cost_usd", "duration_seconds_total",
    "mean_cost_per_run_usd", "mean_cost_per_reviewer_call_usd",
    "mean_duration_per_run_seconds", "usable_runs",
]


def _filled(v) -> bool:
    return v is not None and str(v).strip() != ""


def _is_true(v) -> bool:
    return str(v).strip().lower() == "true"


def _num(v) -> float:
    try:
        return float(str(v).strip())
    except (TypeError, ValueError):
        return 0.0


def _audit_run(run_id: str, technique: str) -> Dict[str, object]:
    usage = RUNS_DIR / run_id / "llm_usage.csv"
    row = {"dataset": DATASET, "run_id": run_id, "technique": technique}
    if not usage.exists():
        row.update({
            "usage_file_exists": "false", "row_count": 0, "reviewer_call_count": 0,
            "reviewer_id_filled_for_reviewer_calls": "n/a",
            "usage_available_true_count": 0, "input_tokens_total": 0,
            "output_tokens_total": 0, "total_tokens_total": 0,
            "total_cost_usd": 0, "duration_seconds_total": 0,
            "usable_for_cost_analysis": "false",
            "notes": "kein llm_usage.csv (Run nicht ausgeführt)",
        })
        return row

    with usage.open("r", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))

    reviewer_rows = [r for r in rows if r.get("phase", "").strip() == REVIEWER_PHASE]
    reviewer_ids_ok = bool(reviewer_rows) and all(_filled(r.get("reviewer_id")) for r in reviewer_rows)
    usage_true = [r for r in rows if _is_true(r.get("usage_available"))]
    usable = any(
        _is_true(r.get("usage_available")) and all(_filled(r.get(c)) for c in COST_CRITICAL)
        for r in rows
    )
    notes = []
    if not usage_true:
        notes.append("keine usage_available=true Zeile")
    if reviewer_rows and not reviewer_ids_ok:
        notes.append("Reviewer-Calls ohne reviewer_id")
    elif reviewer_rows:
        notes.append("reviewer_id bei Reviewer-Calls gefüllt")

    row.update({
        "usage_file_exists": "true",
        "row_count": len(rows),
        "reviewer_call_count": len(reviewer_rows),
        "reviewer_id_filled_for_reviewer_calls": "true" if reviewer_ids_ok else ("false" if reviewer_rows else "n/a"),
        "usage_available_true_count": len(usage_true),
        "input_tokens_total": int(sum(_num(r.get("input_tokens")) for r in rows)),
        "output_tokens_total": int(sum(_num(r.get("output_tokens")) for r in rows)),
        "total_tokens_total": int(sum(_num(r.get("total_tokens")) for r in rows)),
        "total_cost_usd": round(sum(_num(r.get("total_cost")) for r in rows), 8),
        "duration_seconds_total": round(sum(_num(r.get("duration_seconds")) for r in rows), 6),
        "usable_for_cost_analysis": "true" if usable else "false",
        "notes": "; ".join(notes),
    })
    return row


def main() -> int:
    if not MANIFEST.exists():
        raise SystemExit(f"[costed_audit] Manifest fehlt: {MANIFEST}")
    with MANIFEST.open("r", encoding="utf-8") as fh:
        manifest = list(csv.DictReader(fh))

    summary_rows = [_audit_run(r["run_id"], r["technique"]) for r in manifest]

    SUMMARY_OUT.parent.mkdir(parents=True, exist_ok=True)
    with SUMMARY_OUT.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=SUMMARY_COLS)
        w.writeheader()
        for r in summary_rows:
            w.writerow({c: r.get(c, "") for c in SUMMARY_COLS})

    # Aggregation je Technik
    by_tech: Dict[str, List[Dict[str, object]]] = defaultdict(list)
    for r in summary_rows:
        by_tech[str(r["technique"])].append(r)

    agg_rows = []
    for tech, rs in sorted(by_tech.items()):
        completed = [r for r in rs if r["usage_file_exists"] == "true"]
        runs_completed = len(completed)
        calls_total = sum(int(r["row_count"]) for r in completed)
        reviewer_calls_total = sum(int(r["reviewer_call_count"]) for r in completed)
        input_total = sum(int(r["input_tokens_total"]) for r in completed)
        output_total = sum(int(r["output_tokens_total"]) for r in completed)
        total_total = sum(int(r["total_tokens_total"]) for r in completed)
        cost_total = round(sum(float(r["total_cost_usd"]) for r in completed), 8)
        dur_total = round(sum(float(r["duration_seconds_total"]) for r in completed), 6)
        usable_runs = sum(1 for r in completed if r["usable_for_cost_analysis"] == "true")
        agg_rows.append({
            "dataset": DATASET, "technique": tech,
            "runs_completed": runs_completed,
            "calls_total": calls_total,
            "reviewer_calls_total": reviewer_calls_total,
            "input_tokens_total": input_total,
            "output_tokens_total": output_total,
            "total_tokens_total": total_total,
            "total_cost_usd": cost_total,
            "duration_seconds_total": dur_total,
            "mean_cost_per_run_usd": round(cost_total / runs_completed, 8) if runs_completed else 0,
            "mean_cost_per_reviewer_call_usd": round(cost_total / reviewer_calls_total, 8) if reviewer_calls_total else 0,
            "mean_duration_per_run_seconds": round(dur_total / runs_completed, 6) if runs_completed else 0,
            "usable_runs": usable_runs,
        })

    with BY_TECH_OUT.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=BY_TECH_COLS)
        w.writeheader()
        for r in agg_rows:
            w.writerow({c: r.get(c, "") for c in BY_TECH_COLS})

    completed_total = sum(1 for r in summary_rows if r["usage_file_exists"] == "true")
    print(f"[costed_audit] {len(summary_rows)} Runs geprüft, {completed_total} mit llm_usage.csv.")
    print(f"[costed_audit] -> {SUMMARY_OUT}")
    print(f"[costed_audit] -> {BY_TECH_OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
