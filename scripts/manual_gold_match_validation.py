#!/usr/bin/env python3
"""Zusätzliche (Plausibilitäts-)Validierung der automatischen Gold-Matches.

Hintergrund
-----------
Das automatische Matching gegen den Goldstandard (``DefectMatcher`` /
``scripts/union_gold_coverage.py``) entscheidet maßgeblich über eine
Textähnlichkeit der Beschreibung (geblendet mit Positions- und
Signal-Gates). Ein Treffer kann dadurch allein wegen ähnlicher
Formulierung zustande kommen, ohne dass tatsächlich derselbe Defekt
gemeint ist.

Dieses Script ist KEINE Änderung des Matchers. Der bestehende Matcher und
alle bestehenden Evaluationsergebnisse bleiben unverändert. Es entsteht
ausschließlich eine zusätzliche Validierungsschicht, die für jeden
automatisch als Gold-Treffer gezählten Match dokumentiert, ob er
plausibel bestätigt (``confirmed``), unsicher (``doubtful``) oder klar
ein anderer Defekt (``rejected``) ist.

Vorgehen
--------
1. Goldstandard nur lesend laden (``GoldLoader``).
2. Die finalen 40 Runs aus ``results/baseline_manifest.csv`` auswählen
   (status==ok, scope_mode==split, Techniken UBR/CBR/PBR).
3. Für Threshold 0.65 und 0.60 die automatisch gematchten Gold-Treffer mit
   exakt demselben ``DefectMatcher`` rekonstruieren – pro Run pro Reviewer.
4. Für jeden EXACT/PARTIAL-Match die zugehörige LLM-Defektmeldung
   (aus ``raw_defects_<run_id>.csv``) auflösen.
5. Pro Match eine zusätzliche Validierungszeile mit konservativer
   Plausibilitätsentscheidung erzeugen.

Ausgaben
--------
- ``results/manual_gold_match_validation.csv``          (alle Matches)
- ``results/manual_gold_match_validation_t065.csv``     (nur 0.65)
- ``results/manual_gold_match_validation_t060.csv``     (nur 0.60)
- ``results/manual_gold_match_validation_summary.csv``  (Aggregat je Threshold)

Es werden ausschließlich diese neuen Dateien geschrieben. Bestehende
Ergebnisdateien werden NICHT überschrieben.
"""

from __future__ import annotations

import csv
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Set, Tuple

from rapidfuzz import fuzz

# Projekt-src importierbar machen, damit wir den kanonischen Matcher /
# Loader unverändert wiederverwenden.
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_SRC_DIR = _PROJECT_ROOT / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from fagan_tool.core.schemas import (  # noqa: E402
    Defect,
    FaultType,
    GoldDefect,
    MatchType,
    RiskLevel,
)
from fagan_tool.evaluation import DefectMatcher, GoldLoader  # noqa: E402
from fagan_tool.utils.position_tokens import (  # noqa: E402
    collect_defect_position_tokens,
    extract_domain_tokens,
    extract_position_tokens,
    extract_signal_tokens,
    normalize_desc,
)

# Wir verwenden dieselbe Run-Auswahl / dieselben Loader wie die bestehende
# Coverage-Auswertung, damit die rekonstruierten Treffer deckungsgleich
# sind. Reines Wiederverwenden vorhandener Funktionen (keine Änderung).
from union_gold_coverage import (  # noqa: E402
    _load_baseline_runs,
    _load_raw_defects,
    _normalize_technique,
    _row_to_defect,
)

# --------------------------------------------------------------------------
# Konfiguration
# --------------------------------------------------------------------------

THRESHOLDS = (0.65, 0.60)
SCOPE = "split"        # die finalen 40 Runs (UBR/CBR split)
N_FILTER = "all"
TOTAL_GOLD = 36        # Bezugsgröße für confirmed Recall (s. Coverage-Output)

MANIFEST = _PROJECT_ROOT / "results" / "baseline_manifest.csv"
GOLD_XLS = _PROJECT_ROOT / "artifacts" / "gold" / "Faults_List_In_ver6.xls"
RESULTS_DIR = _PROJECT_ROOT / "results"

DETAIL_OUT = RESULTS_DIR / "manual_gold_match_validation.csv"
SUMMARY_OUT = RESULTS_DIR / "manual_gold_match_validation_summary.csv"
DETAIL_OUT_T065 = RESULTS_DIR / "manual_gold_match_validation_t065.csv"
DETAIL_OUT_T060 = RESULTS_DIR / "manual_gold_match_validation_t060.csv"

DETAIL_COLS = [
    "threshold",
    "technique",
    "run_id",
    "reviewer_id",
    "llm_defect_id",
    "gold_id",
    "gold_risk",
    "gold_description",
    "gold_location",
    "llm_description",
    "llm_position",
    "llm_page_hint",
    "llm_entity",
    "similarity_score",
    "same_or_compatible_location",
    "same_or_compatible_signal_or_entity",
    "description_supports_same_defect",
    "validation_decision",
    "validation_confidence",
    "validation_reason",
]

# Generische Formulierungen, die für sich genommen KEINEN konkreten Defekt
# identifizieren. Tauchen sie ohne konkreten Kontext (Signal/Entität) auf,
# darf höchstens `doubtful` vergeben werden.
GENERIC_PHRASES = (
    "missing signal",
    "signal is missing",
    "missing message",
    "message is missing",
    "wrong flow",
    "incorrect flow",
    "missing parameter",
    "parameter is missing",
    "not implemented",
    "is missing",
)

# Schwellen für die qualitative (NICHT für die Match-) Beurteilung der
# Beschreibung. Bewusst eigene, dokumentierte Werte – KEINE alten
# Matcher-Thresholds.
DESC_SUPPORT_YES = 0.55      # token_sort_ratio: deutliche Beschreibungsnähe
DESC_SUPPORT_PARTIAL = 0.35  # token_sort_ratio: teilweise Beschreibungsnähe
DESC_CONFIRM_MIN = 0.40      # Mindest-Beschreibungsnähe für `confirmed`
DESC_NO_SIGNAL_CONFIRM = 0.80  # ohne Signale: hohe Nähe nötig (wie Matcher-Gate 3)


# --------------------------------------------------------------------------
# Validierungslogik (konservativ)
# --------------------------------------------------------------------------


def _norm(text: str) -> str:
    return (text or "").lower().strip()


def _most_specific_tokens(tokens: Set[str]) -> Set[str]:
    """Gold-Positions-Tokens mit höchster Granularität (analog Matcher)."""
    if not tokens:
        return set()

    def spec(token: str) -> int:
        if token.startswith("Table"):
            return 2
        return len(token.split("."))

    max_spec = max(spec(t) for t in tokens)
    return {t for t in tokens if spec(t) == max_spec}


def _looks_generic(description: str) -> bool:
    d = _norm(description)
    return any(p in d for p in GENERIC_PHRASES)


def validate_match(found: Defect, gold: GoldDefect) -> Dict[str, object]:
    """Konservative Plausibilitätsbewertung eines einzelnen Matches.

    Gibt die Felder same_or_compatible_location,
    same_or_compatible_signal_or_entity, description_supports_same_defect,
    validation_decision, validation_confidence, validation_reason und das
    abgeleitete llm_entity zurück.

    Grundprinzip (gemäß Vorgabe):
      * Reine Textähnlichkeit reicht NICHT für `confirmed`.
      * Nennt Gold ein Signal/eine Entität, muss die LLM-Meldung dasselbe
        Signal exakt nennen, sonst höchstens `doubtful`.
      * Nennt Gold KEIN Signal, ist `confirmed` nur bei sehr hoher
        Beschreibungsnähe UND spezifisch passender Location möglich.
      * `rejected` nur, wenn klar ein anderer Defekt erkennbar ist.
      * Im Zweifel `doubtful`.
    """
    # --- Positions-/Location-Analyse (gleiche Helfer wie der Matcher) ---
    found_pos = collect_defect_position_tokens(
        found.position,
        getattr(found, "original_position", None),
        getattr(found, "position_canonical", None),
    )
    gold_pos = set(extract_position_tokens(gold.position))
    pos_overlap = found_pos & gold_pos
    most_specific = _most_specific_tokens(gold_pos)
    hits_specific = bool(pos_overlap & most_specific)

    if not pos_overlap:
        location_grade = "no"
    elif hits_specific or len(pos_overlap) >= 2:
        location_grade = "yes"
    else:
        location_grade = "partial"

    # --- Signal-/Entitäts-Analyse ---
    found_signals = extract_signal_tokens(found.description)
    ev = found.evidence if isinstance(found.evidence, str) else ""
    if ev:
        found_signals |= extract_signal_tokens(ev)
    gold_signals = extract_signal_tokens(gold.description)

    found_domain = extract_domain_tokens(found_signals)
    gold_domain = extract_domain_tokens(gold_signals)
    signal_exact = found_signals & gold_signals
    domain_overlap = found_domain & gold_domain

    both_signals = bool(found_signals) and bool(gold_signals)
    neither_signals = not found_signals and not gold_signals
    one_side_signals = not both_signals and not neither_signals

    llm_entity = ", ".join(sorted(found_signals))

    if signal_exact:
        signal_grade = "yes"            # identisch benanntes Signal/Entität
    elif both_signals and len(domain_overlap) >= 2:
        signal_grade = "partial"        # geteilte Sub-Tokens, kein exakter Name
    elif neither_signals:
        signal_grade = "n/a"            # keine Signale auf beiden Seiten
    elif one_side_signals:
        # Eine Seite nennt ein Signal: prüfen, ob dessen Domäne in der
        # Beschreibung der anderen Seite auftaucht.
        if found_signals and not gold_signals:
            other = set(normalize_desc(gold.description))
            ok = bool(found_domain & other)
        else:
            other = set(normalize_desc(found.description))
            ok = bool(gold_domain & other)
        signal_grade = "partial" if ok else "weak"
    else:
        signal_grade = "weak"

    # --- Beschreibungsnähe (eigene qualitative Beurteilung) ---
    desc_sim = fuzz.token_sort_ratio(_norm(found.description), _norm(gold.description)) / 100.0
    generic = _looks_generic(found.description) and not found_signals
    if desc_sim >= DESC_SUPPORT_YES and not generic:
        desc_grade = "yes"
    elif desc_sim >= DESC_SUPPORT_PARTIAL:
        desc_grade = "partial"
    else:
        desc_grade = "weak"

    # --- Entscheidung (konservativ) ---
    decision = "doubtful"
    confidence = "low"
    reasons: List[str] = []

    gold_names_signal = bool(gold_signals)

    if gold_names_signal:
        if (
            signal_grade == "yes"
            and location_grade == "yes"
            and desc_sim >= DESC_CONFIRM_MIN
            and not generic
        ):
            decision = "confirmed"
            confidence = "high"
            reasons.append("exaktes Signal geteilt, Location spezifisch passend, Beschreibung stützt")
        elif (
            both_signals
            and not signal_exact
            and len(domain_overlap) < 2
        ):
            # Beide Seiten nennen Signale, aber keinerlei gemeinsame Domäne
            # -> deutet auf einen anderen konkreten Defekt hin.
            decision = "rejected"
            confidence = "medium"
            reasons.append("beide Seiten nennen Signale ohne gemeinsame Entität -> vermutlich anderer Defekt")
        else:
            decision = "doubtful"
            confidence = "low"
            if signal_grade != "yes":
                reasons.append("Gold nennt Signal/Entität, LLM-Meldung nennt es nicht exakt")
            if location_grade != "yes":
                reasons.append("Location nur teilweise/unspezifisch kompatibel")
            if generic:
                reasons.append("Beschreibung überwiegend generisch (z. B. 'missing signal')")
            if not reasons:
                reasons.append("Kontext nicht eindeutig genug für eine Bestätigung")
    else:
        # Gold nennt kein Signal -> Identifikation über Beschreibung + Location.
        if (
            desc_sim >= DESC_NO_SIGNAL_CONFIRM
            and location_grade == "yes"
            and not generic
        ):
            decision = "confirmed"
            confidence = "high"
            reasons.append("kein Gold-Signal; sehr hohe Beschreibungsnähe und spezifisch passende Location")
        else:
            decision = "doubtful"
            confidence = "low"
            if desc_sim < DESC_NO_SIGNAL_CONFIRM:
                reasons.append("kein Gold-Signal; Beschreibungsnähe nicht hoch genug für Bestätigung")
            if location_grade != "yes":
                reasons.append("Location nur teilweise/unspezifisch kompatibel")
            if generic:
                reasons.append("Beschreibung überwiegend generisch")
            if not reasons:
                reasons.append("Kontext nicht eindeutig genug für eine Bestätigung")

    return {
        "llm_entity": llm_entity,
        "same_or_compatible_location": location_grade,
        "same_or_compatible_signal_or_entity": signal_grade,
        "description_supports_same_defect": desc_grade,
        "validation_decision": decision,
        "validation_confidence": confidence,
        "validation_reason": "; ".join(reasons),
        "_desc_sim": desc_sim,
    }


# --------------------------------------------------------------------------
# Match-Rekonstruktion
# --------------------------------------------------------------------------


def reconstruct_matches(
    threshold: float,
    runs: Sequence[Tuple[str, str, int]],
    gold: Sequence[GoldDefect],
) -> List[Dict[str, object]]:
    """Alle EXACT/PARTIAL Gold-Matches für einen Threshold rekonstruieren.

    Liefert eine Zeile pro (run, reviewer, LLM-Defekt -> Gold) Match.
    """
    matcher = DefectMatcher(description_threshold=threshold)
    gold_by_id = {g.id: g for g in gold}
    rows: List[Dict[str, object]] = []

    for run_id, tech, _n in runs:
        raw_rows = _load_raw_defects(RESULTS_DIR / f"raw_defects_{run_id}.csv")
        if not raw_rows:
            continue
        # nach Reviewer gruppieren (Matcher arbeitet pro Reviewer, wie in der
        # bestehenden Coverage-Auswertung).
        by_reviewer: Dict[str, List[Dict[str, str]]] = defaultdict(list)
        for r in raw_rows:
            by_reviewer[(r.get("reviewer_id") or "").strip()].append(r)

        for rid, r_rows in by_reviewer.items():
            if not rid:
                continue
            # found-Defekte + Rückbezug auf die Rohzeile
            found_defects: List[Defect] = []
            raw_by_found: Dict[str, Dict[str, str]] = {}
            for rr in r_rows:
                d = _row_to_defect(rr)
                found_defects.append(d)
                raw_by_found[d.id] = rr

            matches, _stats = matcher.match(found_defects, list(gold))
            for m in matches:
                if m.match_type not in (MatchType.EXACT, MatchType.PARTIAL):
                    continue
                if not m.gold_id:
                    continue
                gold_def = gold_by_id.get(m.gold_id)
                if gold_def is None:
                    continue
                raw = raw_by_found.get(m.found_id, {})
                found_obj = next((f for f in found_defects if f.id == m.found_id), None)
                if found_obj is None:
                    continue

                v = validate_match(found_obj, gold_def)
                rows.append(
                    {
                        "threshold": f"{threshold:.2f}",
                        "technique": _normalize_technique(tech),
                        "run_id": run_id,
                        "reviewer_id": rid,
                        "llm_defect_id": m.found_id,
                        "gold_id": gold_def.id,
                        "gold_risk": gold_def.risk.value,
                        "gold_description": gold_def.description,
                        "gold_location": gold_def.position,
                        "llm_description": raw.get("description_raw", ""),
                        "llm_position": raw.get("position", ""),
                        "llm_page_hint": raw.get("page_hint", ""),
                        "llm_entity": v["llm_entity"],
                        "similarity_score": f"{m.similarity_score:.4f}",
                        "same_or_compatible_location": v["same_or_compatible_location"],
                        "same_or_compatible_signal_or_entity": v["same_or_compatible_signal_or_entity"],
                        "description_supports_same_defect": v["description_supports_same_defect"],
                        "validation_decision": v["validation_decision"],
                        "validation_confidence": v["validation_confidence"],
                        "validation_reason": v["validation_reason"],
                    }
                )
    return rows


# --------------------------------------------------------------------------
# Aggregation auf Gold-Ebene
# --------------------------------------------------------------------------

_DECISION_RANK = {"confirmed": 3, "doubtful": 2, "rejected": 1}


def aggregate_gold_decision(decisions: Sequence[str]) -> str:
    """Beste (am stärksten bestätigende) Entscheidung über alle Matches
    eines Gold-Defekts. Wird ein Gold-Defekt von mindestens einem Match
    plausibel bestätigt, gilt er als ``confirmed``."""
    if not decisions:
        return "none"
    return max(decisions, key=lambda d: _DECISION_RANK.get(d, 0))


def build_summary(
    all_rows: Sequence[Dict[str, object]],
    gold: Sequence[GoldDefect],
) -> List[Dict[str, object]]:
    gold_risk = {g.id: g.risk.value for g in gold}
    summary_rows: List[Dict[str, object]] = []

    for threshold in THRESHOLDS:
        thr = f"{threshold:.2f}"
        rows = [r for r in all_rows if r["threshold"] == thr]

        # Match-Ebene
        n_matches = len(rows)
        match_conf = sum(1 for r in rows if r["validation_decision"] == "confirmed")
        match_doubt = sum(1 for r in rows if r["validation_decision"] == "doubtful")
        match_rej = sum(1 for r in rows if r["validation_decision"] == "rejected")

        # Gold-Ebene (Union-TP): je Gold-ID die beste Entscheidung
        decisions_by_gold: Dict[str, List[str]] = defaultdict(list)
        for r in rows:
            decisions_by_gold[str(r["gold_id"])].append(str(r["validation_decision"]))

        gold_decision = {
            gid: aggregate_gold_decision(decs) for gid, decs in decisions_by_gold.items()
        }
        automatic_ids = sorted(gold_decision.keys(), key=lambda x: int(x) if x.isdigit() else x)
        confirmed_ids = [g for g in automatic_ids if gold_decision[g] == "confirmed"]
        doubtful_ids = [g for g in automatic_ids if gold_decision[g] == "doubtful"]
        rejected_ids = [g for g in automatic_ids if gold_decision[g] == "rejected"]

        def _risk_counts(ids: Sequence[str]) -> Dict[str, int]:
            c = {"A": 0, "B": 0, "C": 0}
            for gid in ids:
                rk = gold_risk.get(gid, "")
                if rk in c:
                    c[rk] += 1
            return c

        auto_rc = _risk_counts(automatic_ids)
        conf_rc = _risk_counts(confirmed_ids)

        summary_rows.append(
            {
                "threshold": thr,
                "total_gold": TOTAL_GOLD,
                # Match-Ebene
                "n_matches_validated": n_matches,
                "match_confirmed": match_conf,
                "match_doubtful": match_doubt,
                "match_rejected": match_rej,
                # Gold/Union-Ebene (klar getrennt: automatisch vs. validiert)
                "automatic_union_tp": len(automatic_ids),
                "confirmed_union_tp": len(confirmed_ids),
                "doubtful_union_tp": len(doubtful_ids),
                "rejected_union_tp": len(rejected_ids),
                "automatic_recall": f"{len(automatic_ids) / TOTAL_GOLD:.4f}",
                "confirmed_recall": f"{len(confirmed_ids) / TOTAL_GOLD:.4f}",
                # Gold-ID-Listen
                "automatic_gold_ids": " ".join(automatic_ids),
                "confirmed_gold_ids": " ".join(confirmed_ids),
                "doubtful_gold_ids": " ".join(doubtful_ids),
                "rejected_gold_ids": " ".join(rejected_ids),
                # A/B/C-Zählung
                "automatic_A": auto_rc["A"],
                "automatic_B": auto_rc["B"],
                "automatic_C": auto_rc["C"],
                "confirmed_A": conf_rc["A"],
                "confirmed_B": conf_rc["B"],
                "confirmed_C": conf_rc["C"],
            }
        )
    return summary_rows


# --------------------------------------------------------------------------
# Writer
# --------------------------------------------------------------------------


def _write_csv(path: Path, cols: Sequence[str], rows: Sequence[Dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(cols))
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in cols})


def main() -> int:
    if not MANIFEST.exists():
        print(f"[manual_val] Manifest fehlt: {MANIFEST}", file=sys.stderr)
        return 1
    if not GOLD_XLS.exists():
        print(f"[manual_val] Goldstandard fehlt: {GOLD_XLS}", file=sys.stderr)
        return 1

    runs = _load_baseline_runs(MANIFEST, n_filter=N_FILTER, scope=SCOPE)
    print(f"[manual_val] {len(runs)} Runs ausgewählt (scope={SCOPE}, n={N_FILTER}).")

    gold = GoldLoader(str(GOLD_XLS)).load()
    print(
        f"[manual_val] Gold geladen: total={len(gold)}, "
        f"A={sum(1 for g in gold if g.risk == RiskLevel.A)}, "
        f"B={sum(1 for g in gold if g.risk == RiskLevel.B)}, "
        f"C={sum(1 for g in gold if g.risk == RiskLevel.C)}"
    )

    all_rows: List[Dict[str, object]] = []
    for thr in THRESHOLDS:
        rows = reconstruct_matches(thr, runs, gold)
        gold_ids = sorted({str(r["gold_id"]) for r in rows}, key=lambda x: int(x) if x.isdigit() else x)
        print(
            f"[manual_val] t={thr:.2f}: {len(rows)} Match-Zeilen, "
            f"{len(gold_ids)} eindeutige Gold-IDs ({' '.join(gold_ids)})"
        )
        all_rows.extend(rows)

    # Sortierung: Threshold, Gold-ID, Technik, Run, Reviewer
    def _sort_key(r: Dict[str, object]):
        gid = str(r["gold_id"])
        return (
            str(r["threshold"]),
            int(gid) if gid.isdigit() else 10**9,
            str(r["technique"]),
            str(r["run_id"]),
            str(r["reviewer_id"]),
        )

    all_rows.sort(key=_sort_key)

    _write_csv(DETAIL_OUT, DETAIL_COLS, all_rows)
    _write_csv(DETAIL_OUT_T065, DETAIL_COLS, [r for r in all_rows if r["threshold"] == "0.65"])
    _write_csv(DETAIL_OUT_T060, DETAIL_COLS, [r for r in all_rows if r["threshold"] == "0.60"])

    summary_rows = build_summary(all_rows, gold)
    summary_cols = [
        "threshold",
        "total_gold",
        "n_matches_validated",
        "match_confirmed",
        "match_doubtful",
        "match_rejected",
        "automatic_union_tp",
        "confirmed_union_tp",
        "doubtful_union_tp",
        "rejected_union_tp",
        "automatic_recall",
        "confirmed_recall",
        "automatic_gold_ids",
        "confirmed_gold_ids",
        "doubtful_gold_ids",
        "rejected_gold_ids",
        "automatic_A",
        "automatic_B",
        "automatic_C",
        "confirmed_A",
        "confirmed_B",
        "confirmed_C",
    ]
    _write_csv(SUMMARY_OUT, summary_cols, summary_rows)

    print(f"[manual_val] Geschrieben: {DETAIL_OUT}")
    print(f"[manual_val] Geschrieben: {DETAIL_OUT_T065}")
    print(f"[manual_val] Geschrieben: {DETAIL_OUT_T060}")
    print(f"[manual_val] Geschrieben: {SUMMARY_OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
