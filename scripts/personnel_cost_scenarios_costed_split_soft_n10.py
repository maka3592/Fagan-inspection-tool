#!/usr/bin/env python3
"""Literaturbasierte Personalkosten-Szenarien als Kontext zu den gemessenen
LLM-API-Kosten des Datensatzes ``costed_split_soft_n10``.

WICHTIG:
- Die LLM-API-Kosten sind REAL gemessen (listenpreisbasiert, USD).
- Die Personalkosten sind eine LITERATURBASIERTE SCHÄTZUNG zur
  Kontextualisierung — KEINE gemessenen Personalkosten dieses Experiments.
- Es findet KEINE USD/EUR-Verrechnung in einer einzigen Kennzahl statt:
  API-Kosten bleiben USD, Personalkosten bleiben EUR, getrennt berichtet.

Eingabe:
  - results/costed_split_soft_n10/costs/cost_per_gold_tp_summary.csv

Ausgaben:
  - results/costed_split_soft_n10/costs/personnel_cost_scenarios.csv
  - results/costed_split_soft_n10/costs/api_vs_personnel_cost_context.csv

Goldstandard und Evaluation-Code werden nicht berührt.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Dict, List

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
COSTS_DIR = _PROJECT_ROOT / "results" / "costed_split_soft_n10" / "costs"

COST_PER_TP = COSTS_DIR / "cost_per_gold_tp_summary.csv"
OUT_SCENARIOS = COSTS_DIR / "personnel_cost_scenarios.csv"
OUT_CONTEXT = COSTS_DIR / "api_vs_personnel_cost_context.csv"

DATASET = "costed_split_soft_n10"

# Literaturbasierte Personalkosten-Szenarien (EUR). Schätzung, nicht gemessen.
SCENARIOS = [
    {
        "scenario": "low",
        "staff_hours_per_defect": 0.8,
        "labour_cost_eur_per_hour": 43.40,
        "personnel_cost_eur_per_defect": 34.72,
        "source_basis": "Applicon-style lower bound / major problem found and fixed",
    },
    {
        "scenario": "medium",
        "staff_hours_per_defect": 1.58,
        "labour_cost_eur_per_hour": 43.40,
        "personnel_cost_eur_per_defect": 68.57,
        "source_basis": "ICL design-defect effort",
    },
    {
        "scenario": "high",
        "staff_hours_per_defect": 2.7,
        "labour_cost_eur_per_hour": 43.40,
        "personnel_cost_eur_per_defect": 117.18,
        "source_basis": "Lockheed found-and-fixed upper scenario",
    },
]

SCENARIO_COLS = [
    "scenario", "staff_hours_per_defect", "labour_cost_eur_per_hour",
    "personnel_cost_eur_per_defect", "source_basis",
]

CONTEXT_COLS = [
    "dataset", "threshold", "automatic_union_tp", "human_confirmed_union_tp",
    "human_doubtful_union_tp", "total_api_cost_usd",
    "api_cost_per_automatic_gold_tp_usd", "api_cost_per_human_confirmed_gold_tp_usd",
    "scenario", "staff_hours_per_defect", "labour_cost_eur_per_hour",
    "personnel_cost_eur_per_defect", "personnel_cost_for_human_confirmed_tp_eur",
    "personnel_cost_for_automatic_tp_eur", "interpretation_note",
]

INTERPRETATION = (
    "API cost is measured (listenpreisbasiert, USD, reale Tokenusage); "
    "personnel cost is a literature-based estimate (EUR). Keine USD/EUR-Verrechnung."
)


def _read_csv(path: Path) -> List[Dict[str, str]]:
    if not path.exists():
        raise SystemExit(f"[personnel] Eingabe fehlt: {path}")
    with path.open("r", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _i(value, default: int = 0) -> int:
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return default


def main() -> int:
    summary = _read_csv(COST_PER_TP)

    # 1. Szenarien-Datei
    COSTS_DIR.mkdir(parents=True, exist_ok=True)
    with OUT_SCENARIOS.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=SCENARIO_COLS)
        w.writeheader()
        for s in SCENARIOS:
            w.writerow({c: s[c] for c in SCENARIO_COLS})

    # 2. Kontext-Datei: pro Threshold × Szenario
    context_rows = []
    for r in summary:
        thr = str(r["threshold"]).strip()
        auto_tp = _i(r["automatic_union_tp"])
        conf_tp = _i(r["human_confirmed_union_tp"])
        doubt_tp = _i(r["human_doubtful_union_tp"])
        for s in SCENARIOS:
            per_defect = float(s["personnel_cost_eur_per_defect"])
            context_rows.append({
                "dataset": DATASET,
                "threshold": thr,
                "automatic_union_tp": auto_tp,
                "human_confirmed_union_tp": conf_tp,
                "human_doubtful_union_tp": doubt_tp,
                "total_api_cost_usd": r.get("total_cost_usd", ""),
                "api_cost_per_automatic_gold_tp_usd": r.get("cost_per_automatic_gold_tp_usd", ""),
                "api_cost_per_human_confirmed_gold_tp_usd": r.get("cost_per_human_confirmed_gold_tp_usd", ""),
                "scenario": s["scenario"],
                "staff_hours_per_defect": s["staff_hours_per_defect"],
                "labour_cost_eur_per_hour": s["labour_cost_eur_per_hour"],
                "personnel_cost_eur_per_defect": per_defect,
                "personnel_cost_for_human_confirmed_tp_eur": round(conf_tp * per_defect, 2),
                "personnel_cost_for_automatic_tp_eur": round(auto_tp * per_defect, 2),
                "interpretation_note": INTERPRETATION,
            })

    with OUT_CONTEXT.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=CONTEXT_COLS)
        w.writeheader()
        for r in context_rows:
            w.writerow({c: r.get(c, "") for c in CONTEXT_COLS})

    print(f"[personnel] {len(SCENARIOS)} Szenarien -> {OUT_SCENARIOS}")
    print(f"[personnel] {len(context_rows)} Kontext-Zeilen -> {OUT_CONTEXT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
