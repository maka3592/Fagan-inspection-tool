#!/usr/bin/env python3
"""Kompakte Review-Tabelle auf Gold-ID-Ebene für die manuelle Gegenprüfung.

Hintergrund
-----------
Für die von der Betreuung geforderte echte manuelle Gegenprüfung der
automatisch gematchten Gold-Treffer sollen nicht alle Match-Zeilen einzeln
geprüft werden. Stattdessen wird hier aus
``results/manual_gold_match_validation.csv`` eine kompakte Review-Datei
erzeugt, die **pro eindeutiger Kombination aus ``threshold`` und
``gold_id`` genau eine Zeile** enthält – mit dem besten repräsentativen
Kandidaten.

Dies ist KEINE Änderung des Matchers, der Evaluation oder des
Goldstandards. Es werden ausschließlich zwei neue Dateien geschrieben:

- ``results/manual_gold_match_review_sheet.csv``       (eine Zeile je gold_id)
- ``results/manual_gold_match_review_candidates.csv``  (alle Kandidaten, sortiert)

Kandidatenauswahl je (threshold, gold_id)
------------------------------------------
1. bevorzugt ``validation_decision = confirmed``
2. sonst ``doubtful`` (sonst ``rejected``)
3. innerhalb der Gruppe höchster ``similarity_score``
4. bei Gleichstand der Kandidat mit spezifischerer Location/Entity

Die Spalten ``human_decision`` und ``human_reason`` bleiben leer und
dienen der manuellen Eintragung.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Dict, List, Tuple

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
RESULTS_DIR = _PROJECT_ROOT / "results"

INPUT_DETAIL = RESULTS_DIR / "manual_gold_match_validation.csv"
REVIEW_SHEET_OUT = RESULTS_DIR / "manual_gold_match_review_sheet.csv"
REVIEW_CANDIDATES_OUT = RESULTS_DIR / "manual_gold_match_review_candidates.csv"

# Rang der automatischen Entscheidung (höher = stärker bestätigend).
DECISION_RANK = {"confirmed": 3, "doubtful": 2, "rejected": 1}

SHEET_COLS = [
    "threshold",
    "gold_id",
    "gold_risk",
    "gold_description",
    "gold_location",
    "auto_decision_best",
    "candidate_count",
    "techniques",
    "best_similarity_score",
    "example_run_id",
    "example_reviewer_id",
    "example_llm_defect_id",
    "example_llm_description",
    "example_llm_position",
    "example_llm_page_hint",
    "example_llm_entity",
    "auto_location_check",
    "auto_signal_entity_check",
    "auto_description_check",
    "auto_validation_reason",
    "human_decision",
    "human_reason",
]

# Kandidaten-Datei: Detail-Spalten plus ein paar Kontextfelder unverändert.
CANDIDATE_COLS = [
    "threshold",
    "gold_id",
    "gold_risk",
    "validation_decision",
    "similarity_score",
    "technique",
    "run_id",
    "reviewer_id",
    "llm_defect_id",
    "llm_description",
    "llm_position",
    "llm_page_hint",
    "llm_entity",
    "same_or_compatible_location",
    "same_or_compatible_signal_or_entity",
    "description_supports_same_defect",
    "validation_reason",
    "gold_description",
    "gold_location",
]


def _to_float(value: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _location_specificity(position: str) -> int:
    """Höhere Granularität der Positionsangabe -> höherer Wert.

    Z. B. ``3.4.2`` (3 Ebenen) spezifischer als ``3.2`` (2 Ebenen).
    ``Table N`` zählt als moderat spezifisch (2).
    """
    if not position:
        return 0
    best = 0
    for raw in str(position).replace(";", ",").split(","):
        tok = raw.strip()
        if not tok:
            continue
        low = tok.lower()
        if low.startswith("table"):
            best = max(best, 2)
            continue
        if any(ch.isdigit() for ch in tok):
            best = max(best, len([p for p in tok.split(".") if p.strip()]))
    return best


def _entity_specificity(entity: str) -> int:
    """Anzahl der genannten Signale/Entitäten (mehr = spezifischer)."""
    if not entity:
        return 0
    return len([e for e in str(entity).split(",") if e.strip()])


def _tiebreak_key(row: Dict[str, str]) -> Tuple[int, int, int]:
    """Sekundärschlüssel bei gleichem similarity_score: spezifischere
    Location/Entity bevorzugen, dann längere Beschreibung als Tiebreaker."""
    return (
        _location_specificity(row.get("llm_position", "")),
        _entity_specificity(row.get("llm_entity", "")),
        len(row.get("llm_description", "") or ""),
    )


def _candidate_sort_key(row: Dict[str, str]) -> Tuple:
    """Sortierung der Kandidaten-Datei:
    threshold, gold_id, decision (confirmed zuerst), similarity desc."""
    gid = str(row.get("gold_id", ""))
    return (
        str(row.get("threshold", "")),
        int(gid) if gid.isdigit() else 10 ** 9,
        -DECISION_RANK.get(str(row.get("validation_decision", "")), 0),
        -_to_float(row.get("similarity_score", "")),
    )


def _select_best(rows: List[Dict[str, str]]) -> Dict[str, str]:
    """Besten repräsentativen Kandidaten gemäß Vorgaben wählen."""
    # 1. beste vorhandene Entscheidungsgruppe bestimmen
    best_rank = max(DECISION_RANK.get(str(r.get("validation_decision", "")), 0) for r in rows)
    group = [r for r in rows if DECISION_RANK.get(str(r.get("validation_decision", "")), 0) == best_rank]
    # 2./3./4. höchster similarity_score, dann spezifischere Location/Entity
    group.sort(
        key=lambda r: (_to_float(r.get("similarity_score", "")),) + _tiebreak_key(r),
        reverse=True,
    )
    return group[0]


def main() -> int:
    if not INPUT_DETAIL.exists():
        raise SystemExit(f"[review_sheet] Input fehlt: {INPUT_DETAIL}")

    with INPUT_DETAIL.open("r", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    if not rows:
        raise SystemExit("[review_sheet] Keine Eingabezeilen.")

    # nach (threshold, gold_id) gruppieren
    groups: Dict[Tuple[str, str], List[Dict[str, str]]] = {}
    for r in rows:
        key = (str(r.get("threshold", "")), str(r.get("gold_id", "")))
        groups.setdefault(key, []).append(r)

    sheet_rows: List[Dict[str, object]] = []
    for (thr, gid), grp in groups.items():
        best = _select_best(grp)
        techniques = ", ".join(sorted({str(r.get("technique", "")).strip() for r in grp if r.get("technique")}))
        sheet_rows.append(
            {
                "threshold": thr,
                "gold_id": gid,
                "gold_risk": best.get("gold_risk", ""),
                "gold_description": best.get("gold_description", ""),
                "gold_location": best.get("gold_location", ""),
                "auto_decision_best": best.get("validation_decision", ""),
                "candidate_count": len(grp),
                "techniques": techniques,
                "best_similarity_score": best.get("similarity_score", ""),
                "example_run_id": best.get("run_id", ""),
                "example_reviewer_id": best.get("reviewer_id", ""),
                "example_llm_defect_id": best.get("llm_defect_id", ""),
                "example_llm_description": best.get("llm_description", ""),
                "example_llm_position": best.get("llm_position", ""),
                "example_llm_page_hint": best.get("llm_page_hint", ""),
                "example_llm_entity": best.get("llm_entity", ""),
                "auto_location_check": best.get("same_or_compatible_location", ""),
                "auto_signal_entity_check": best.get("same_or_compatible_signal_or_entity", ""),
                "auto_description_check": best.get("description_supports_same_defect", ""),
                "auto_validation_reason": best.get("validation_reason", ""),
                "human_decision": "",
                "human_reason": "",
            }
        )

    # Review-Sheet sortieren: threshold, gold_id
    def _sheet_sort(r: Dict[str, object]) -> Tuple:
        gid = str(r["gold_id"])
        return (str(r["threshold"]), int(gid) if gid.isdigit() else 10 ** 9)

    sheet_rows.sort(key=_sheet_sort)

    REVIEW_SHEET_OUT.parent.mkdir(parents=True, exist_ok=True)
    with REVIEW_SHEET_OUT.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=SHEET_COLS)
        w.writeheader()
        for r in sheet_rows:
            w.writerow({c: r.get(c, "") for c in SHEET_COLS})

    # Kandidaten-Datei (alle Kandidaten, sortiert)
    cand_rows = sorted(rows, key=_candidate_sort_key)
    with REVIEW_CANDIDATES_OUT.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=CANDIDATE_COLS)
        w.writeheader()
        for r in cand_rows:
            w.writerow({c: r.get(c, "") for c in CANDIDATE_COLS})

    print(f"[review_sheet] {len(sheet_rows)} Zeilen -> {REVIEW_SHEET_OUT}")
    print(f"[review_sheet] {len(cand_rows)} Kandidaten -> {REVIEW_CANDIDATES_OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
