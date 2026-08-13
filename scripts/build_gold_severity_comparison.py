#!/usr/bin/env python3
"""Build a severity-class (A/B/C) comparison table for the costed_split_soft_n10
dataset.

Purpose
-------
Closes the open gap from the requirements audit (requirement 9): a quantitative
table that maps the *manually confirmed* LLM gold matches to the gold severity
classes (A / B / C) and compares them against the gold distribution.

What it does NOT do
-------------------
- No new runs, no re-evaluation, no matcher changes.
- It only reuses the unmodified GoldLoader (src/fagan_tool/evaluation/) to read
  the gold standard, and reads already-existing result files for the confirmed
  gold IDs.

Data sources
------------
- Gold standard / risk levels: artifacts/gold/Faults_List_In_ver6.xls
  (read via the existing, unmodified GoldLoader).
- Confirmed gold IDs (human-validated): preferentially read from
  results/costed_split_soft_n10/final_costed_results_summary.json
  (key: human_validated_coverage.<t>.human_confirmed_gold_ids).
  If that source is unavailable, a controlled fallback to the known IDs from
  the audit is used and clearly flagged in the output.

Outputs
-------
- results/costed_split_soft_n10/manual_gold_match/gold_severity_comparison.csv
- results/costed_split_soft_n10/manual_gold_match/gold_severity_comparison.md
"""

from __future__ import annotations

import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

# Make the package importable without installation.
REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from fagan_tool.evaluation.gold_loader import GoldLoader  # noqa: E402

# --- Paths -----------------------------------------------------------------
GOLD_PATH = REPO_ROOT / "artifacts/gold/Faults_List_In_ver6.xls"
SUMMARY_JSON = REPO_ROOT / "results/costed_split_soft_n10/final_costed_results_summary.json"
OUT_DIR = REPO_ROOT / "results/costed_split_soft_n10/manual_gold_match"
OUT_CSV = OUT_DIR / "gold_severity_comparison.csv"
OUT_MD = OUT_DIR / "gold_severity_comparison.md"

# Expected gold distribution (acts as an integrity check, NOT as input data).
EXPECTED_DISTRIBUTION = {"A": 13, "B": 13, "C": 10}

# Controlled fallback (only used if the summary JSON cannot be parsed).
FALLBACK_CONFIRMED = {
    "0.65": ["8", "28", "31"],
    "0.60": ["8", "25", "27", "28", "31"],
}

MAIN_T = "0.65"
SENS_T = "0.60"
CLASSES = ["A", "B", "C"]


def load_gold_risk_map() -> dict[str, str]:
    """id -> risk level ('A'/'B'/'C'/'UNK') using the unmodified GoldLoader."""
    defects = GoldLoader(GOLD_PATH).load()
    return {d.id: d.risk.value for d in defects}


def load_confirmed_ids() -> tuple[dict[str, list[str]], str]:
    """Return (confirmed_ids_by_threshold, source_label).

    Prefers final_costed_results_summary.json; falls back to known IDs.
    """
    try:
        data = json.loads(SUMMARY_JSON.read_text(encoding="utf-8"))
        hvc = data["human_validated_coverage"]
        confirmed = {}
        for t in (MAIN_T, SENS_T):
            ids_str = hvc[t]["human_confirmed_gold_ids"]
            confirmed[t] = [tok for tok in str(ids_str).split() if tok]
        source = f"derived from {SUMMARY_JSON.relative_to(REPO_ROOT)} (human_validated_coverage)"
        return confirmed, source
    except (FileNotFoundError, KeyError, json.JSONDecodeError) as exc:
        source = (
            f"CONTROLLED FALLBACK to known audit IDs "
            f"(summary JSON unavailable: {type(exc).__name__})"
        )
        return dict(FALLBACK_CONFIRMED), source


def build_rows(
    risk_map: dict[str, str],
    confirmed: dict[str, list[str]],
) -> tuple[list[dict], dict[str, dict[str, list[str]]]]:
    """Build per-class rows plus the confirmed IDs grouped by class/threshold."""
    gold_total = Counter(risk_map.values())

    # confirmed_by_class[threshold][class] = [ids...]
    confirmed_by_class: dict[str, dict[str, list[str]]] = {
        t: defaultdict(list) for t in (MAIN_T, SENS_T)
    }
    for t in (MAIN_T, SENS_T):
        for gid in confirmed[t]:
            cls = risk_map.get(gid, "UNK")
            confirmed_by_class[t][cls].append(gid)

    def tp(t: str, cls: str) -> int:
        return len(confirmed_by_class[t][cls])

    def coverage(tp_count: int, total: int) -> float:
        return round(tp_count / total, 4) if total else 0.0

    rows: list[dict] = []

    # Single classes A, B, C
    for cls in CLASSES:
        total = gold_total.get(cls, 0)
        tp65, tp60 = tp(MAIN_T, cls), tp(SENS_T, cls)
        rows.append(
            {
                "class": cls,
                "gold_total": total,
                "confirmed_tp_t065": tp65,
                "coverage_t065": coverage(tp65, total),
                "confirmed_ids_t065": " ".join(sorted(confirmed_by_class[MAIN_T][cls], key=int)),
                "confirmed_tp_t060": tp60,
                "coverage_t060": coverage(tp60, total),
                "confirmed_ids_t060": " ".join(sorted(confirmed_by_class[SENS_T][cls], key=int)),
            }
        )

    # A+B combined
    ab_total = gold_total.get("A", 0) + gold_total.get("B", 0)
    ab_tp65 = tp(MAIN_T, "A") + tp(MAIN_T, "B")
    ab_tp60 = tp(SENS_T, "A") + tp(SENS_T, "B")
    ab_ids65 = sorted(confirmed_by_class[MAIN_T]["A"] + confirmed_by_class[MAIN_T]["B"], key=int)
    ab_ids60 = sorted(confirmed_by_class[SENS_T]["A"] + confirmed_by_class[SENS_T]["B"], key=int)
    rows.append(
        {
            "class": "A+B",
            "gold_total": ab_total,
            "confirmed_tp_t065": ab_tp65,
            "coverage_t065": coverage(ab_tp65, ab_total),
            "confirmed_ids_t065": " ".join(ab_ids65),
            "confirmed_tp_t060": ab_tp60,
            "coverage_t060": coverage(ab_tp60, ab_total),
            "confirmed_ids_t060": " ".join(ab_ids60),
        }
    )

    # Total (over A/B/C only; UNK would surface separately)
    tot_total = sum(gold_total.get(c, 0) for c in CLASSES)
    tot_tp65 = sum(tp(MAIN_T, c) for c in CLASSES)
    tot_tp60 = sum(tp(SENS_T, c) for c in CLASSES)
    tot_ids65 = sorted(
        [g for c in CLASSES for g in confirmed_by_class[MAIN_T][c]], key=int
    )
    tot_ids60 = sorted(
        [g for c in CLASSES for g in confirmed_by_class[SENS_T][c]], key=int
    )
    rows.append(
        {
            "class": "Gesamt",
            "gold_total": tot_total,
            "confirmed_tp_t065": tot_tp65,
            "coverage_t065": coverage(tot_tp65, tot_total),
            "confirmed_ids_t065": " ".join(tot_ids65),
            "confirmed_tp_t060": tot_tp60,
            "coverage_t060": coverage(tot_tp60, tot_total),
            "confirmed_ids_t060": " ".join(tot_ids60),
        }
    )

    return rows, confirmed_by_class


def pct(x: float) -> str:
    return f"{x * 100:.2f} %"


def write_csv(rows: list[dict]) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    fields = [
        "class",
        "gold_total",
        "confirmed_tp_t065",
        "coverage_t065",
        "confirmed_ids_t065",
        "confirmed_tp_t060",
        "coverage_t060",
        "confirmed_ids_t060",
    ]
    with OUT_CSV.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def render_md_table(rows: list[dict]) -> str:
    lines = [
        "| Klasse | Gold total | Confirmed LLM TP (t=0,65) | Coverage (t=0,65) "
        "| Confirmed LLM TP (t=0,60) | Coverage (t=0,60) |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for r in rows:
        lines.append(
            f"| {r['class']} | {r['gold_total']} | {r['confirmed_tp_t065']} | "
            f"{pct(r['coverage_t065'])} | {r['confirmed_tp_t060']} | "
            f"{pct(r['coverage_t060'])} |"
        )
    return "\n".join(lines)


def render_ids_block(confirmed_by_class: dict[str, dict[str, list[str]]]) -> str:
    def fmt(t: str) -> str:
        parts = []
        for cls in CLASSES:
            ids = sorted(confirmed_by_class[t][cls], key=int)
            parts.append(f"  - {cls}: {' '.join(ids) if ids else '—'}")
        return "\n".join(parts)

    return (
        f"- **t = 0,65 (Hauptthreshold):**\n{fmt(MAIN_T)}\n"
        f"- **t = 0,60 (Sensitivität):**\n{fmt(SENS_T)}"
    )


def write_result_md(rows: list[dict], confirmed_by_class, source: str) -> None:
    table = render_md_table(rows)
    ids_block = render_ids_block(confirmed_by_class)
    content = (
        "# Gold Severity Comparison (Maschinen-Output)\n\n"
        f"Quelle der bestätigten IDs: {source}.\n\n"
        f"{table}\n\n"
        "## Bestätigte Gold-IDs je Klasse\n\n"
        f"{ids_block}\n"
    )
    OUT_MD.write_text(content, encoding="utf-8")


def main() -> int:
    risk_map = load_gold_risk_map()

    # Integrity check: reproduce expected gold distribution BEFORE writing.
    dist = Counter(risk_map.values())
    actual = {c: dist.get(c, 0) for c in CLASSES}
    dist_ok = actual == EXPECTED_DISTRIBUTION
    total_gold = sum(dist.values())

    print("Gold distribution (A/B/C):", actual, "| total:", total_gold)
    if not dist_ok or total_gold != 36:
        print(
            "ERROR: Gold distribution mismatch. "
            f"Expected {EXPECTED_DISTRIBUTION} (total 36), got {actual} (total {total_gold}).",
            file=sys.stderr,
        )
        print("Aborting without writing outputs.", file=sys.stderr)
        return 1

    confirmed, source = load_confirmed_ids()
    print("Confirmed IDs source:", source)
    print("Confirmed t=0.65:", confirmed[MAIN_T])
    print("Confirmed t=0.60:", confirmed[SENS_T])

    rows, confirmed_by_class = build_rows(risk_map, confirmed)

    # Warn on any confirmed ID that has no A/B/C class (would be excluded from totals).
    unknown = [
        gid
        for t in (MAIN_T, SENS_T)
        for gid in confirmed[t]
        if risk_map.get(gid, "UNK") not in CLASSES
    ]
    if unknown:
        print(f"WARNING: confirmed IDs without A/B/C class: {sorted(set(unknown))}",
              file=sys.stderr)

    write_csv(rows)
    write_result_md(rows, confirmed_by_class, source)

    print("\nWritten:")
    for p in (OUT_CSV, OUT_MD):
        print(" -", p.relative_to(REPO_ROOT))

    print("\nTable:")
    print(render_md_table(rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
