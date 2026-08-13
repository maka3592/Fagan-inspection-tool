#!/usr/bin/env python3
"""Fachliche Auswertung des instrumentierten Datensatzes ``costed_split_soft_n10``.

Wrapper, der die bestehende Evaluations-/Aggregationslogik unverändert
wiederverwendet, aber ALLE Outputs ausschließlich nach
``results/costed_split_soft_n10/`` schreibt. Bestehende
Baseline-Ergebnisse (``results/union_gold_*``, ``results/manual_gold_match_*``,
``results/saturation_*`` usw.) werden NICHT überschrieben.

Vorgehen:
- Gut parametrisierte Skripte (extract/dedupe/saturation/union_gold_coverage/
  gold_at_saturation/fault_share_plots) werden via Subprocess mit
  ``--out-dir/--outdir/--results-dir`` in den neuen Ordner gelenkt.
- Die fest verdrahteten Manual-Gold-Match-Skripte werden importiert und ihre
  Modul-Pfadkonstanten auf den neuen Ordner umgebogen (Monkeypatch), bevor
  ``main()`` aufgerufen wird.

Goldstandard, Matcher und Evaluation-Code bleiben unverändert.
Thresholds: 0.65 (Haupt) und 0.60 (Sensitivität).
"""

from __future__ import annotations

import csv
import importlib.util
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Dict, List

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
GOLD = ROOT / "artifacts" / "gold" / "Faults_List_In_ver6.xls"

SRC_MANIFEST = ROOT / "results" / "costed_split_soft_n10_manifest.csv"
USAGE_SUMMARY = ROOT / "results" / "costed_split_soft_n10_usage_summary.csv"
USAGE_BYTECH = ROOT / "results" / "costed_split_soft_n10_usage_by_technique.csv"

OUT = ROOT / "results" / "costed_split_soft_n10"
DATASET = "costed_split_soft_n10"
THRESHOLDS = [("0.65", "t065"), ("0.60", "t060")]

# Unterordner
D_RAW = OUT / "raw_defects"
D_DEDUPE_WORK = OUT / "_dedupe_work"          # Arbeitsverzeichnis (flach)
D_PRD = OUT / "per_reviewer_dedupe"
D_UNION = OUT / "union_defects"
D_INC = OUT / "incremental"
D_SAT = OUT / "saturation"
D_UG = {"t065": OUT / "union_gold_t065", "t060": OUT / "union_gold_t060"}
D_GAS = OUT / "gold_at_saturation"
D_FS = OUT / "fault_share"
D_MGM = OUT / "manual_gold_match"
D_COSTS = OUT / "costs"

COMPAT_MANIFEST = OUT / "costed_baseline_manifest.csv"   # für die Skripte
EVAL_MANIFEST = OUT / "evaluation_manifest.csv"          # Aufgabe 3


def _mkdirs() -> None:
    for d in [OUT, D_RAW, D_DEDUPE_WORK, D_PRD, D_UNION, D_INC, D_SAT,
              D_UG["t065"], D_UG["t060"], D_GAS, D_FS, D_MGM, D_COSTS]:
        d.mkdir(parents=True, exist_ok=True)


def _run(cmd: List[str]) -> None:
    print(f"[eval] $ {' '.join(cmd)}")
    proc = subprocess.run(cmd, cwd=str(ROOT))
    if proc.returncode != 0:
        raise SystemExit(f"[eval] Schritt fehlgeschlagen (rc={proc.returncode}): {' '.join(cmd)}")


def _read_csv(path: Path) -> List[Dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


# ---------------------------------------------------------------------------
# Manifeste
# ---------------------------------------------------------------------------

def build_compat_manifest() -> None:
    """Baseline-kompatibles Manifest (Spalten wie results/baseline_manifest.csv)
    für die bestehenden Skripte. status=ok, scope_mode=split, n_reviewers=10."""
    rows = _read_csv(SRC_MANIFEST)
    cols = ["timestamp", "run_id", "technique", "n_reviewers", "scope_mode",
            "config_path", "run_path", "metrics_path", "status"]
    with COMPAT_MANIFEST.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for r in rows:
            run_id = r["run_id"]
            w.writerow({
                "timestamp": "", "run_id": run_id, "technique": r["technique"],
                "n_reviewers": r.get("reviewers", "10"), "scope_mode": "split",
                "config_path": r.get("config_path", ""),
                "run_path": f"runs/{run_id}", "metrics_path": "", "status": "ok",
            })
    print(f"[eval] Kompat-Manifest -> {COMPAT_MANIFEST}")


def build_eval_manifest() -> None:
    """Aufgabe 3: evaluation_manifest.csv aus Plan-Manifest + Usage-Summary."""
    plan = _read_csv(SRC_MANIFEST)
    usage = {r["run_id"]: r for r in _read_csv(USAGE_SUMMARY)}
    cols = ["dataset", "run_id", "technique", "reviewers", "run_path",
            "usage_file", "usable_for_cost_analysis"]
    with EVAL_MANIFEST.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for r in plan:
            rid = r["run_id"]
            u = usage.get(rid, {})
            w.writerow({
                "dataset": DATASET, "run_id": rid, "technique": r["technique"],
                "reviewers": r.get("reviewers", "10"),
                "run_path": f"runs/{rid}",
                "usage_file": f"runs/{rid}/llm_usage.csv",
                "usable_for_cost_analysis": u.get("usable_for_cost_analysis", ""),
            })
    print(f"[eval] Eval-Manifest -> {EVAL_MANIFEST}")


def copy_costs() -> None:
    """Aufgabe 5: Usage-Extrakte in costs/."""
    if USAGE_BYTECH.exists():
        shutil.copy2(USAGE_BYTECH, D_COSTS / "usage_by_technique.csv")
    if USAGE_SUMMARY.exists():
        shutil.copy2(USAGE_SUMMARY, D_COSTS / "usage_by_run.csv")
    print(f"[eval] Kosten-Extrakte -> {D_COSTS}")


# ---------------------------------------------------------------------------
# Pipeline (Subprocess auf bestehende Skripte)
# ---------------------------------------------------------------------------

def run_pipeline() -> None:
    py = sys.executable
    man = str(COMPAT_MANIFEST)

    # 1. Raw defects pro Run -> raw_defects/
    _run([py, str(SCRIPTS / "extract_defects_raw.py"),
          "--from-baseline", man, "--runs-dir", "runs", "--out-dir", str(D_RAW)])

    # 2. Per-reviewer dedupe / union defects / incremental -> Arbeitsdir
    _run([py, str(SCRIPTS / "dedupe_analysis.py"),
          "--from-baseline", man, "--runs-dir", "runs", "--out-dir", str(D_DEDUPE_WORK)])
    # in die benannten Unterordner sortieren
    for f in sorted(D_DEDUPE_WORK.glob("per_reviewer_dedupe_*.csv")):
        shutil.copy2(f, D_PRD / f.name)
    for f in sorted(D_DEDUPE_WORK.glob("union_defects_*.csv")):
        shutil.copy2(f, D_UNION / f.name)
    for f in sorted(D_DEDUPE_WORK.glob("incremental_*.csv")):
        shutil.copy2(f, D_INC / f.name)
    fq = D_DEDUPE_WORK / "defect_frequency_summary.csv"
    if fq.exists():
        shutil.copy2(fq, D_PRD / "defect_frequency_summary.csv")

    # 3. Reviewer-count saturation (liest union_defects_/incremental_ aus Arbeitsdir)
    _run([py, str(SCRIPTS / "saturation_analysis.py"),
          "--from-baseline", man, "--out-dir", str(D_DEDUPE_WORK),
          "--per-run-out", str(D_SAT / "saturation_points_per_run.csv"),
          "--summary-out", str(D_SAT / "saturation_points_summary.csv")])

    # 4. Union gold coverage @ 0.65 / 0.60
    for thr, tag in THRESHOLDS:
        _run([py, str(SCRIPTS / "union_gold_coverage.py"),
              "--from-baseline", man, "--gold", str(GOLD),
              "--results-dir", str(D_RAW), "--outdir", str(D_UG[tag]),
              "--scope", "split", "--n-reviewers", "all", "--mode", "pooled",
              "--threshold", thr])

    # 5. Gold at saturation @ 0.65 / 0.60
    for thr, tag in THRESHOLDS:
        _run([py, str(SCRIPTS / "gold_at_saturation.py"),
              "--from-baseline", man, "--gold", str(GOLD),
              "--results-dir", str(D_RAW),
              "--saturation-file", str(D_SAT / "saturation_points_per_run.csv"),
              "--per-run-out", str(D_GAS / f"gold_at_saturation_{tag}_per_run.csv"),
              "--summary-out", str(D_GAS / f"gold_at_saturation_{tag}_summary.csv"),
              "--threshold", thr])

    # 6. Fault share A/B @ 0.65 / 0.60
    for thr, tag in THRESHOLDS:
        _run([py, str(SCRIPTS / "fault_share_plots.py"),
              "--from-baseline", man, "--gold", str(GOLD),
              "--results-dir", str(D_RAW), "--outdir", str(D_FS / tag),
              "--scope", "split", "--threshold", thr])


# ---------------------------------------------------------------------------
# Manual gold match (fest verdrahtete Skripte -> Monkeypatch auf neuen Ordner)
# ---------------------------------------------------------------------------

def _load_script_module(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / filename)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def run_manual_gold_match() -> None:
    # Validierung: Manifest + raw_defects des NEUEN Datensatzes, Output -> manual_gold_match/
    mgmv = _load_script_module("mgmv_costed", "manual_gold_match_validation.py")
    mgmv.MANIFEST = COMPAT_MANIFEST
    mgmv.RESULTS_DIR = D_RAW
    mgmv.DETAIL_OUT = D_MGM / "manual_gold_match_validation.csv"
    mgmv.SUMMARY_OUT = D_MGM / "manual_gold_match_validation_summary.csv"
    mgmv.DETAIL_OUT_T065 = D_MGM / "manual_gold_match_validation_t065.csv"
    mgmv.DETAIL_OUT_T060 = D_MGM / "manual_gold_match_validation_t060.csv"
    print("[eval] Manual-Gold-Match-Validierung (neuer Datensatz) ...")
    mgmv.main()

    # Review-Sheet auf Basis der neuen Validierung
    bms = _load_script_module("bms_costed", "build_manual_gold_match_review_sheet.py")
    bms.INPUT_DETAIL = D_MGM / "manual_gold_match_validation.csv"
    bms.REVIEW_SHEET_OUT = D_MGM / "manual_gold_match_review_sheet.csv"
    bms.REVIEW_CANDIDATES_OUT = D_MGM / "manual_gold_match_review_candidates.csv"
    print("[eval] Manual-Gold-Match-Review-Sheet (neuer Datensatz) ...")
    bms.main()


# ---------------------------------------------------------------------------
# Zusammenfassung
# ---------------------------------------------------------------------------

def print_summary() -> None:
    print("\n========== Zusammenfassung costed_split_soft_n10 ==========")
    for thr, tag in THRESHOLDS:
        cov = D_UG[tag] / f"union_gold_coverage_pooled_split_nall_{tag}.csv"
        rows = _read_csv(cov)
        if rows:
            r = rows[0]
            print(f"[t={thr}] tp_union={r.get('tp_union')}/{r.get('total_gold')} "
                  f"recall_union={r.get('recall_union')} | "
                  f"tp_ubr={r.get('tp_ubr')} tp_cbr={r.get('tp_cbr')}")
        ids_file = D_UG[tag] / f"union_gold_ids_pooled_split_nall_{tag}.csv"
        idrows = _read_csv(ids_file)
        hit = sorted([r["gold_id"] for r in idrows if r.get("hit_union") == "1"],
                     key=lambda x: int(x) if x.isdigit() else 10**9)
        print(f"[t={thr}] automatisch gematchte Gold-IDs (union): {' '.join(hit)}")
    sat = _read_csv(D_SAT / "saturation_points_summary.csv")
    if sat:
        print(f"[saturation] {sat[0]}")
    review = D_MGM / "manual_gold_match_review_sheet.csv"
    print(f"[manual] review sheet erzeugt: {review.exists()} ({review})")


def main() -> int:
    if not SRC_MANIFEST.exists():
        raise SystemExit(f"[eval] Plan-Manifest fehlt: {SRC_MANIFEST}")
    _mkdirs()
    build_compat_manifest()
    build_eval_manifest()
    copy_costs()
    run_pipeline()
    run_manual_gold_match()
    print_summary()
    print(f"\n[eval] Fertig. Alle Outputs unter {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
