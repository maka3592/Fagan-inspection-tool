#!/usr/bin/env python3
"""Kosten- und Laufzeitmetriken je Gold-TP für ``costed_split_soft_n10``.

Setzt die real gemessenen, listenpreisbasierten API-Kosten (USD) sowie
technische Laufzeit und Tokenusage in Relation zu

  * automatisch gematchten Gold-Faults und
  * manuell bestätigten Gold-Faults

bei den Thresholds 0.65 und 0.60.

Eingaben:
  - results/costed_split_soft_n10/costs/usage_by_technique.csv
  - results/costed_split_soft_n10/costs/usage_by_run.csv
  - results/costed_split_soft_n10/manual_gold_match/manual_gold_match_human_summary.csv

Ausgaben:
  - results/costed_split_soft_n10/costs/cost_per_gold_tp_summary.csv
  - results/costed_split_soft_n10/costs/cost_by_technique.csv

Hinweise:
  - Kosten sind LISTENPREISBASIERTE API-Kosten (USD) auf Basis REAL
    gemessener Tokenusage — KEINE Billing-Dashboard-Rechnungspositionen.
  - ``total_duration_seconds`` ist technische API-/Tool-Laufzeit, NICHT
    menschlicher Inspektionsaufwand.

Goldstandard und Evaluation-Code werden nicht berührt.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Dict, List, Optional

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
COSTS_DIR = _PROJECT_ROOT / "results" / "costed_split_soft_n10" / "costs"
MGM_DIR = _PROJECT_ROOT / "results" / "costed_split_soft_n10" / "manual_gold_match"

USAGE_BY_TECH = COSTS_DIR / "usage_by_technique.csv"
USAGE_BY_RUN = COSTS_DIR / "usage_by_run.csv"
HUMAN_SUMMARY = MGM_DIR / "manual_gold_match_human_summary.csv"

OUT_SUMMARY = COSTS_DIR / "cost_per_gold_tp_summary.csv"
OUT_BY_TECH = COSTS_DIR / "cost_by_technique.csv"

DATASET = "costed_split_soft_n10"
TOTAL_GOLD = 36

SUMMARY_COLS = [
    "dataset", "threshold", "total_gold",
    "automatic_union_tp", "human_confirmed_union_tp",
    "human_doubtful_union_tp", "human_rejected_union_tp",
    "automatic_recall", "human_confirmed_recall",
    "total_cost_usd", "total_duration_seconds", "total_tokens_total",
    "input_tokens_total", "output_tokens_total",
    "cost_per_automatic_gold_tp_usd",
    "cost_per_human_confirmed_gold_tp_usd",
    "cost_per_human_confirmed_or_doubtful_gold_tp_usd",
    "duration_per_automatic_gold_tp_seconds",
    "duration_per_human_confirmed_gold_tp_seconds",
    "tokens_per_automatic_gold_tp",
    "tokens_per_human_confirmed_gold_tp",
    "confirmed_gold_ids", "doubtful_gold_ids", "rejected_gold_ids",
]

BY_TECH_COLS = [
    "dataset", "technique", "runs_completed", "calls_total",
    "reviewer_calls_total", "total_cost_usd", "total_duration_seconds",
    "total_tokens_total", "mean_cost_per_run_usd",
    "mean_cost_per_reviewer_call_usd", "mean_duration_per_run_seconds",
    "mean_tokens_per_run", "mean_tokens_per_reviewer_call",
]


def _read_csv(path: Path) -> List[Dict[str, str]]:
    if not path.exists():
        raise SystemExit(f"[cost] Eingabe fehlt: {path}")
    with path.open("r", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _f(value, default: float = 0.0) -> float:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return default


def _i(value, default: int = 0) -> int:
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return default


def _ratio(num: float, denom: float, digits: int = 8) -> str:
    """Division mit 0-Schutz: leer bei denom==0 (kein Crash)."""
    if denom == 0:
        return ""
    return f"{num / denom:.{digits}f}"


def main() -> int:
    tech_rows = _read_csv(USAGE_BY_TECH)
    human_rows = _read_csv(HUMAN_SUMMARY)
    # usage_by_run nur zur Existenz-/Plausibilitätsprüfung gelesen.
    _ = _read_csv(USAGE_BY_RUN)

    # Datensatzweite Totale über UBR + CBR.
    total_cost = sum(_f(r["total_cost_usd"]) for r in tech_rows)
    total_duration = sum(_f(r["duration_seconds_total"]) for r in tech_rows)
    total_tokens = sum(_i(r["total_tokens_total"]) for r in tech_rows)
    input_tokens = sum(_i(r["input_tokens_total"]) for r in tech_rows)
    output_tokens = sum(_i(r["output_tokens_total"]) for r in tech_rows)

    # --- cost_per_gold_tp_summary ---
    summary_rows = []
    for h in human_rows:
        thr = str(h["threshold"]).strip()
        auto_tp = _i(h["automatic_union_tp"])
        conf_tp = _i(h["human_confirmed_union_tp"])
        doubt_tp = _i(h["human_doubtful_union_tp"])
        rej_tp = _i(h["human_rejected_union_tp"])
        conf_or_doubt = conf_tp + doubt_tp

        summary_rows.append({
            "dataset": DATASET, "threshold": thr, "total_gold": TOTAL_GOLD,
            "automatic_union_tp": auto_tp,
            "human_confirmed_union_tp": conf_tp,
            "human_doubtful_union_tp": doubt_tp,
            "human_rejected_union_tp": rej_tp,
            "automatic_recall": h.get("automatic_recall", ""),
            "human_confirmed_recall": h.get("human_confirmed_recall", ""),
            "total_cost_usd": f"{total_cost:.6f}",
            "total_duration_seconds": f"{total_duration:.6f}",
            "total_tokens_total": total_tokens,
            "input_tokens_total": input_tokens,
            "output_tokens_total": output_tokens,
            "cost_per_automatic_gold_tp_usd": _ratio(total_cost, auto_tp, 6),
            "cost_per_human_confirmed_gold_tp_usd": _ratio(total_cost, conf_tp, 6),
            "cost_per_human_confirmed_or_doubtful_gold_tp_usd": _ratio(total_cost, conf_or_doubt, 6),
            "duration_per_automatic_gold_tp_seconds": _ratio(total_duration, auto_tp, 4),
            "duration_per_human_confirmed_gold_tp_seconds": _ratio(total_duration, conf_tp, 4),
            "tokens_per_automatic_gold_tp": _ratio(total_tokens, auto_tp, 2),
            "tokens_per_human_confirmed_gold_tp": _ratio(total_tokens, conf_tp, 2),
            "confirmed_gold_ids": h.get("human_confirmed_gold_ids", ""),
            "doubtful_gold_ids": h.get("human_doubtful_gold_ids", ""),
            "rejected_gold_ids": h.get("human_rejected_gold_ids", ""),
        })

    OUT_SUMMARY.parent.mkdir(parents=True, exist_ok=True)
    with OUT_SUMMARY.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=SUMMARY_COLS)
        w.writeheader()
        for r in summary_rows:
            w.writerow({c: r.get(c, "") for c in SUMMARY_COLS})

    # --- cost_by_technique ---
    by_tech_rows = []
    for r in tech_rows:
        runs = _i(r["runs_completed"])
        rev_calls = _i(r["reviewer_calls_total"])
        tok = _i(r["total_tokens_total"])
        by_tech_rows.append({
            "dataset": DATASET, "technique": r["technique"],
            "runs_completed": runs,
            "calls_total": _i(r["calls_total"]),
            "reviewer_calls_total": rev_calls,
            "total_cost_usd": f"{_f(r['total_cost_usd']):.6f}",
            "total_duration_seconds": f"{_f(r['duration_seconds_total']):.6f}",
            "total_tokens_total": tok,
            "mean_cost_per_run_usd": _ratio(_f(r["total_cost_usd"]), runs, 8),
            "mean_cost_per_reviewer_call_usd": _ratio(_f(r["total_cost_usd"]), rev_calls, 8),
            "mean_duration_per_run_seconds": _ratio(_f(r["duration_seconds_total"]), runs, 4),
            "mean_tokens_per_run": _ratio(tok, runs, 2),
            "mean_tokens_per_reviewer_call": _ratio(tok, rev_calls, 2),
        })

    with OUT_BY_TECH.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=BY_TECH_COLS)
        w.writeheader()
        for r in by_tech_rows:
            w.writerow({c: r.get(c, "") for c in BY_TECH_COLS})

    print(f"[cost] total_cost_usd={total_cost:.6f} | total_tokens={total_tokens} | total_duration_s={total_duration:.1f}")
    print(f"[cost] -> {OUT_SUMMARY}")
    print(f"[cost] -> {OUT_BY_TECH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
