#!/usr/bin/env python3
"""Trägt die menschlichen Gegenprüfungs-Entscheidungen in das
Review-Sheet des Datensatzes ``costed_split_soft_n10`` ein und erzeugt die
Human-Summary.

Bearbeitet AUSSCHLIESSLICH das neue Sheet unter
``results/costed_split_soft_n10/manual_gold_match/`` — das alte Sheet
``results/manual_gold_match_review_sheet.csv`` wird nicht angefasst.
Goldstandard und Evaluation-Code bleiben unverändert.

Es werden nur die Spalten ``human_decision`` und ``human_reason``
geändert. Das Script bricht ab, wenn eine erwartete
``(threshold, gold_id)``-Kombination fehlt oder eine Sheet-Zeile ohne
Entscheidung übrig bliebe.
"""

from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Tuple

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
MGM_DIR = _PROJECT_ROOT / "results" / "costed_split_soft_n10" / "manual_gold_match"
SHEET = MGM_DIR / "manual_gold_match_review_sheet.csv"
SUMMARY_OUT = MGM_DIR / "manual_gold_match_human_summary.csv"

DATASET = "costed_split_soft_n10"
TOTAL_GOLD = 36
THRESHOLDS = ("0.65", "0.60")
RISKS = ("A", "B", "C")
HUMAN_DECISIONS = ("confirmed", "doubtful", "rejected")

# Menschliche Gegenprüfung (threshold, gold_id) -> (decision, reason).
DECISIONS: Dict[Tuple[str, str], Tuple[str, str]] = {
    ("0.60", "6"): ("rejected", "Gleicher Signalname, aber anderer Defekt: Im Goldstandard fehlt die Information Estimated time im Signal confirm; die LLM-Meldung beschreibt dagegen ein nicht definiertes Confirm-Signal für die Auftragsübermittlung."),
    ("0.60", "7"): ("doubtful", "Gleiche Entität und kompatible Location, aber nicht eindeutig derselbe Defekt: Im Goldstandard stimmen Requirement 3.2.4 und das Design von allocate_car nicht überein; die LLM-Meldung beschreibt ein fehlendes Signal zur Bestätigung der Fahrzeugzuweisung."),
    ("0.60", "8"): ("confirmed", "Gleiches Signal und kompatible Location; die LLM-Meldung beschreibt ausdrücklich das fehlende Cancel_Order-Signal zum Stornieren akzeptierter Aufträge."),
    ("0.60", "25"): ("confirmed", "Gleiche Struktur und sehr naher fehlender Parameter: Im Goldstandard fehlt die Taxi-Nummer beziehungsweise laut Zusatz die Order-Nummer in order_struct; die LLM-Meldung beschreibt eine fehlende Definition von Order_number im Kontext von order_struct."),
    ("0.60", "27"): ("confirmed", "Gleiches Signal und kompatible Location; im Goldstandard fehlen Parameter beim Signal Logged In, und die LLM-Meldung beschreibt konkret, dass beim Login-Signal die Driver Number fehlt."),
    ("0.60", "28"): ("confirmed", "Gleiches Signal und kompatible Location; die LLM-Meldung beschreibt inkonsistente Voice_Msg-Parameter gegenüber den erwarteten Parametern in Table 1 und trifft damit den Kern des Goldstandard-Defekts."),
    ("0.60", "31"): ("confirmed", "Gleiches Signal und kompatible Location; die LLM-Meldung beschreibt ausdrücklich das fehlende Confirm_Voice-Signal."),
    ("0.60", "32"): ("rejected", "Gleicher Signalname und gleiche Location, aber anderer Defekt: Im Goldstandard sollte Start_voice zu send_voice geändert werden; die LLM-Meldung beschreibt dagegen eine unnötige Wiederholung des Signals."),
    ("0.60", "38"): ("rejected", "Gleicher allgemeiner Signalbegriff und gleiche Location, aber anderer Defekt: Im Goldstandard sollte Order zu OrderOper geändert werden und ein Parameter fehlt; die LLM-Meldung beschreibt dagegen ein fehlendes Rejection-Signal."),
    ("0.65", "8"): ("confirmed", "Gleiches Signal und kompatible Location; die LLM-Meldung beschreibt ausdrücklich das fehlende Cancel_Order-Signal zum Stornieren akzeptierter Aufträge."),
    ("0.65", "28"): ("confirmed", "Gleiches Signal und kompatible Location; die LLM-Meldung beschreibt inkonsistente Voice_Msg-Parameter gegenüber den erwarteten Parametern in Table 1 und trifft damit den Kern des Goldstandard-Defekts."),
    ("0.65", "31"): ("confirmed", "Gleiches Signal und kompatible Location; die LLM-Meldung beschreibt ausdrücklich das fehlende Confirm_Voice-Signal."),
    ("0.65", "32"): ("rejected", "Gleicher Signalname und gleiche Location, aber anderer Defekt: Im Goldstandard sollte Start_voice zu send_voice geändert werden; die LLM-Meldung beschreibt dagegen eine unnötige Wiederholung des Signals."),
    ("0.65", "38"): ("rejected", "Gleicher allgemeiner Signalbegriff und gleiche Location, aber anderer Defekt: Im Goldstandard sollte Order zu OrderOper geändert werden und ein Parameter fehlt; die LLM-Meldung beschreibt dagegen ein fehlendes Rejection-Signal."),
}

SUMMARY_COLS = [
    "dataset", "threshold", "total_gold",
    "automatic_union_tp", "automatic_gold_ids",
    "human_confirmed_union_tp", "human_confirmed_gold_ids",
    "human_doubtful_union_tp", "human_doubtful_gold_ids",
    "human_rejected_union_tp", "human_rejected_gold_ids",
    "automatic_recall", "human_confirmed_recall",
    "human_doubtful_recall", "human_rejected_recall",
    "human_confirmed_A", "human_confirmed_B", "human_confirmed_C",
    "human_doubtful_A", "human_doubtful_B", "human_doubtful_C",
    "human_rejected_A", "human_rejected_B", "human_rejected_C",
]


def _norm_thr(value: str) -> str:
    try:
        return f"{float(value):.2f}"
    except (TypeError, ValueError):
        return str(value).strip()


def _sort_ids(ids) -> List[str]:
    return sorted(ids, key=lambda x: int(x) if str(x).isdigit() else 10 ** 9)


def _recall(n: int) -> str:
    return f"{n / TOTAL_GOLD:.4f}"


def apply_decisions() -> List[Dict[str, str]]:
    if not SHEET.exists():
        raise SystemExit(f"[apply] Review-Sheet fehlt: {SHEET}")
    with SHEET.open("r", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        fieldnames = reader.fieldnames or []
        rows = list(reader)

    for col in ("human_decision", "human_reason"):
        if col not in fieldnames:
            raise SystemExit(f"[apply] Spalte fehlt im Sheet: {col}")

    used: set = set()
    missing: List[Tuple[str, str]] = []
    for r in rows:
        key = (_norm_thr(r.get("threshold", "")), str(r.get("gold_id", "")).strip())
        if key in DECISIONS:
            dec, reason = DECISIONS[key]
            r["human_decision"] = dec
            r["human_reason"] = reason
            used.add(key)
        else:
            missing.append(key)

    # Validierungen
    if missing:
        raise SystemExit(f"[apply] Sheet-Zeile(n) ohne erwartete Entscheidung: {missing}")
    not_found = set(DECISIONS) - used
    if not_found:
        raise SystemExit(f"[apply] Erwartete (threshold, gold_id)-Kombination(en) nicht im Sheet: {sorted(not_found)}")
    if len(used) != 14:
        raise SystemExit(f"[apply] Es wurden {len(used)} statt exakt 14 Entscheidungen eingetragen.")
    empty = [(r['threshold'], r['gold_id']) for r in rows if not str(r.get('human_decision', '')).strip()]
    if empty:
        raise SystemExit(f"[apply] Unentschiedene Zeilen verblieben: {empty}")

    with SHEET.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow(r)
    print(f"[apply] 14 Entscheidungen eingetragen -> {SHEET}")
    return rows


def build_summary(rows: List[Dict[str, str]]) -> None:
    by_thr: Dict[str, List[Dict[str, str]]] = defaultdict(list)
    for r in rows:
        by_thr[_norm_thr(r.get("threshold", ""))].append(r)

    out_rows = []
    for thr in THRESHOLDS:
        grp = by_thr.get(thr, [])
        automatic_ids = [str(r["gold_id"]).strip() for r in grp]
        by_dec: Dict[str, List[Dict[str, str]]] = {d: [] for d in HUMAN_DECISIONS}
        for r in grp:
            dec = str(r.get("human_decision", "")).strip().lower()
            if dec in by_dec:
                by_dec[dec].append(r)

        def ids(dec: str) -> List[str]:
            return [str(r["gold_id"]).strip() for r in by_dec[dec]]

        def risk_count(dec: str, risk: str) -> int:
            return sum(1 for r in by_dec[dec] if str(r.get("gold_risk", "")).strip().upper() == risk)

        row = {
            "dataset": DATASET, "threshold": thr, "total_gold": TOTAL_GOLD,
            "automatic_union_tp": len(set(automatic_ids)),
            "automatic_gold_ids": " ".join(_sort_ids(set(automatic_ids))),
            "automatic_recall": _recall(len(set(automatic_ids))),
        }
        for dec in HUMAN_DECISIONS:
            d_ids = ids(dec)
            row[f"human_{dec}_union_tp"] = len(d_ids)
            row[f"human_{dec}_gold_ids"] = " ".join(_sort_ids(d_ids))
            row[f"human_{dec}_recall"] = _recall(len(d_ids))
            for risk in RISKS:
                row[f"human_{dec}_{risk}"] = risk_count(dec, risk)
        out_rows.append(row)

    with SUMMARY_OUT.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=SUMMARY_COLS)
        w.writeheader()
        for r in out_rows:
            w.writerow({c: r.get(c, "") for c in SUMMARY_COLS})
    print(f"[apply] Human-Summary -> {SUMMARY_OUT}")


def main() -> int:
    rows = apply_decisions()
    build_summary(rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
