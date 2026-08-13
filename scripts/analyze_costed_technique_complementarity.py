#!/usr/bin/env python3
"""Complementarity-/Combination-Auswertung für ``costed_split_soft_n10``.

Vergleicht UBR allein, CBR allein und die **nachträgliche Ergebnis-Union**
UBR ∪ CBR bei den Thresholds 0.65 und 0.60 — bezüglich automatisch
gematchter und manuell bestätigter Gold-Faults sowie Kosten.

WICHTIG: ``UBR_union_CBR`` ist eine **post-hoc Set-Union** der pro-Technik
gefundenen Gold-IDs, **KEIN** echter Hybrid-Reading-Ansatz. Ein echter
Hybrid müsste als eigene Reading-Technik operationalisiert und neu
ausgeführt werden.

Eingaben (nur vorhandene costed-Ergebnisse, keine neuen Runs):
  - results/costed_split_soft_n10/union_gold_t065/union_gold_ids_pooled_split_nall_t065.csv
  - results/costed_split_soft_n10/union_gold_t060/union_gold_ids_pooled_split_nall_t060.csv
  - results/costed_split_soft_n10/manual_gold_match/manual_gold_match_human_summary.csv
  - results/costed_split_soft_n10/costs/cost_by_technique.csv

Ausgaben:
  - results/costed_split_soft_n10/technique_complementarity/technique_gold_overlap_summary.csv
  - results/costed_split_soft_n10/technique_complementarity/technique_overlap_sets.csv

Goldstandard und Evaluation-Code werden nicht berührt.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Dict, List, Set

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
BASE = _PROJECT_ROOT / "results" / "costed_split_soft_n10"
OUT_DIR = BASE / "technique_complementarity"
COST_BY_TECH = BASE / "costs" / "cost_by_technique.csv"
HUMAN_SUMMARY = BASE / "manual_gold_match" / "manual_gold_match_human_summary.csv"

DATASET = "costed_split_soft_n10"
TOTAL_GOLD = 36
THRESHOLDS = [("0.65", "t065"), ("0.60", "t060")]

SUMMARY_COLS = [
    "dataset", "threshold", "technique_or_combination",
    "automatic_gold_ids", "automatic_tp", "automatic_recall",
    "human_confirmed_gold_ids", "human_confirmed_tp", "human_confirmed_recall",
    "human_doubtful_gold_ids", "human_doubtful_tp",
    "human_rejected_gold_ids", "human_rejected_tp",
    "total_cost_usd", "cost_per_automatic_tp_usd",
    "cost_per_human_confirmed_tp_usd", "note",
]

SETS_COLS = [
    "dataset", "threshold", "ubr_gold_ids", "cbr_gold_ids",
    "shared_gold_ids", "ubr_only_gold_ids", "cbr_only_gold_ids",
    "union_gold_ids", "shared_count", "ubr_only_count", "cbr_only_count",
    "union_count",
]


def _sort_ids(ids) -> List[str]:
    return sorted(set(ids), key=lambda x: int(x) if str(x).isdigit() else 10 ** 9)


def _join(ids) -> str:
    return " ".join(_sort_ids(ids))


def _parse_ids(value: str) -> Set[str]:
    return {tok for tok in str(value or "").split() if tok.strip()}


def _recall(n: int) -> str:
    return f"{n / TOTAL_GOLD:.4f}"


def _ratio(num: float, denom: int, digits: int = 6) -> str:
    if denom == 0:
        return ""
    return f"{num / denom:.{digits}f}"


def _read_csv(path: Path) -> List[Dict[str, str]]:
    if not path.exists():
        raise SystemExit(f"[complement] Eingabe fehlt: {path}")
    with path.open("r", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _technique_ids(tag: str) -> Dict[str, Set[str]]:
    """Liest hit_ubr / hit_cbr / hit_union je Gold-ID aus union_gold_ids."""
    F = BASE / f"union_gold_{tag}" / f"union_gold_ids_pooled_split_nall_{tag}.csv"
    ubr, cbr, union = set(), set(), set()
    for r in _read_csv(F):
        gid = r["gold_id"]
        if r.get("hit_ubr") == "1":
            ubr.add(gid)
        if r.get("hit_cbr") == "1":
            cbr.add(gid)
        if r.get("hit_union") == "1":
            union.add(gid)
    # Defensive: Union mindestens als UBR ∪ CBR.
    union |= (ubr | cbr)
    return {"UBR": ubr, "CBR": cbr, "UBR_union_CBR": union}


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # Kosten je Technik
    cost = {r["technique"].strip().upper(): float(r["total_cost_usd"])
            for r in _read_csv(COST_BY_TECH)}
    cost_ubr = cost.get("UBR", 0.0)
    cost_cbr = cost.get("CBR", 0.0)
    cost_union = round(cost_ubr + cost_cbr, 6)

    # Menschliche Entscheidungen je Threshold (Union-Ebene)
    human = {}
    for r in _read_csv(HUMAN_SUMMARY):
        human[f"{float(r['threshold']):.2f}"] = {
            "confirmed": _parse_ids(r.get("human_confirmed_gold_ids")),
            "doubtful": _parse_ids(r.get("human_doubtful_gold_ids")),
            "rejected": _parse_ids(r.get("human_rejected_gold_ids")),
        }

    summary_rows = []
    sets_rows = []

    for thr, tag in THRESHOLDS:
        tech = _technique_ids(tag)
        h = human.get(thr, {"confirmed": set(), "doubtful": set(), "rejected": set()})

        cost_map = {"UBR": cost_ubr, "CBR": cost_cbr, "UBR_union_CBR": cost_union}
        note_map = {
            "UBR": "UBR allein (automatische Gold-Treffer)",
            "CBR": "CBR allein (automatische Gold-Treffer)",
            "UBR_union_CBR": "post-hoc Ergebnis-Union UBR ∪ CBR; KEIN Hybrid-Reading-Ansatz",
        }

        for combo in ("UBR", "CBR", "UBR_union_CBR"):
            auto_ids = tech[combo]
            conf = auto_ids & h["confirmed"]
            doubt = auto_ids & h["doubtful"]
            rej = auto_ids & h["rejected"]
            c = cost_map[combo]
            summary_rows.append({
                "dataset": DATASET, "threshold": thr,
                "technique_or_combination": combo,
                "automatic_gold_ids": _join(auto_ids),
                "automatic_tp": len(auto_ids),
                "automatic_recall": _recall(len(auto_ids)),
                "human_confirmed_gold_ids": _join(conf),
                "human_confirmed_tp": len(conf),
                "human_confirmed_recall": _recall(len(conf)),
                "human_doubtful_gold_ids": _join(doubt),
                "human_doubtful_tp": len(doubt),
                "human_rejected_gold_ids": _join(rej),
                "human_rejected_tp": len(rej),
                "total_cost_usd": f"{c:.6f}",
                "cost_per_automatic_tp_usd": _ratio(c, len(auto_ids)),
                "cost_per_human_confirmed_tp_usd": _ratio(c, len(conf)),
                "note": note_map[combo],
            })

        ubr, cbr = tech["UBR"], tech["CBR"]
        shared = ubr & cbr
        ubr_only = ubr - cbr
        cbr_only = cbr - ubr
        union = ubr | cbr
        sets_rows.append({
            "dataset": DATASET, "threshold": thr,
            "ubr_gold_ids": _join(ubr), "cbr_gold_ids": _join(cbr),
            "shared_gold_ids": _join(shared),
            "ubr_only_gold_ids": _join(ubr_only),
            "cbr_only_gold_ids": _join(cbr_only),
            "union_gold_ids": _join(union),
            "shared_count": len(shared),
            "ubr_only_count": len(ubr_only),
            "cbr_only_count": len(cbr_only),
            "union_count": len(union),
        })

    out_summary = OUT_DIR / "technique_gold_overlap_summary.csv"
    with out_summary.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=SUMMARY_COLS)
        w.writeheader()
        for r in summary_rows:
            w.writerow({c: r.get(c, "") for c in SUMMARY_COLS})

    out_sets = OUT_DIR / "technique_overlap_sets.csv"
    with out_sets.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=SETS_COLS)
        w.writeheader()
        for r in sets_rows:
            w.writerow({c: r.get(c, "") for c in SETS_COLS})

    print(f"[complement] -> {out_summary}")
    print(f"[complement] -> {out_sets}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
