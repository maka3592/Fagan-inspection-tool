#!/usr/bin/env python3
"""Automatic PBR evaluation for the supplementary dataset costed_pbr_split_soft_n10.

SUPPLEMENTARY ANALYSIS — not part of the UBR/CBR main comparison. Reuses the
CANONICAL matcher (``fagan_tool.evaluation.DefectMatcher``) and ``GoldLoader``
— the same matching used by ``fagan eval`` and ``union_gold_coverage.py`` — so
PBR is evaluated with identical logic. No new matching logic is introduced.

Inputs:
- raw defects per run: results/costed_pbr_split_soft_n10/raw_defects/raw_defects_<run_id>.csv
  (produced by scripts/extract_defects_raw.py, same as UBR/CBR)
- gold: artifacts/gold/Faults_List_In_ver6.xls (evaluation only)
- token/cost: runs/<run_id>/llm_usage.csv

Outputs (all under results/costed_pbr_split_soft_n10/):
- pbr_automatic_coverage.csv         (per threshold: tp, recall, gold ids, A/B/C/A+B)
- costs/pbr_cost_summary.csv         (tokens + list-price API cost)
- (manual validation candidate rows are emitted to pbr_match_candidates.csv)

All automatic matches are CANDIDATES pending manual validation — never reported
as confirmed.
"""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(ROOT / "src"))

from fagan_tool.core.schemas import Defect, FaultType, RiskLevel  # noqa: E402
from fagan_tool.evaluation import DefectMatcher, GoldLoader  # noqa: E402

DATASET = "costed_pbr_split_soft_n10"
OUT = ROOT / "results" / DATASET
RAW = OUT / "raw_defects"
COSTS = OUT / "costs"
GOLD = ROOT / "artifacts" / "gold" / "Faults_List_In_ver6.xls"
RUNS = ROOT / "runs"
THRESHOLDS = [0.65, 0.60]
N_RUNS = 20

# Existing manually-confirmed UBR/CBR union (from the final main comparison).
CONFIRMED_UBR_CBR = {0.65: {"8", "28", "31"}, 0.60: {"8", "25", "27", "28", "31"}}


def _norm_fault(v: str) -> FaultType:
    v = (v or "").strip().upper()
    if v == "M":
        return FaultType.M
    if v == "W":
        return FaultType.W
    return FaultType.UNK


def _row_to_defect(row: dict) -> Defect:
    """Mirror union_gold_coverage._row_to_defect (same Defect construction)."""
    desc = (row.get("description_raw") or "").strip()
    pos = (row.get("position") or "").strip() or "unknown"
    page = (row.get("page_hint") or "").strip() or None
    return Defect(
        id=(row.get("defect_id") or "").strip() or f"raw_{id(row)}",
        position=pos,
        page_hint=page,
        risk=RiskLevel.UNK,
        fault_type=_norm_fault(row.get("fault_type") or ""),
        description=desc,
        evidence=desc,
        confidence=0.8,
        reviewer_id=row.get("reviewer_id") or None,
    )


def _load_run_defects(run_id: str):
    p = RAW / f"raw_defects_{run_id}.csv"
    rows = list(csv.DictReader(p.open(encoding="utf-8"))) if p.exists() else []
    found = [_row_to_defect(r) for r in rows]
    text_by_id = {d.id: (d.description, d.reviewer_id or "") for d in found}
    return found, text_by_id


def main() -> int:
    gold = GoldLoader(GOLD).load()
    id_risk = {g.id: g.risk.value for g in gold}
    total_gold = len(gold)

    run_ids = [f"{DATASET}_{i:03d}" for i in range(1, N_RUNS + 1)]

    # candidate rows: per (threshold, gold_id) keep best-scoring match + run count
    coverage_rows = []
    candidate_rows = []

    for thr in THRESHOLDS:
        matcher = DefectMatcher(description_threshold=thr)  # canonical matcher
        union_ids = set()
        # gold_id -> {best_score, best_run, best_reviewer, best_text, n_runs}
        best = {}
        runs_hitting = defaultdict(set)
        for rid in run_ids:
            found, text_by_id = _load_run_defects(rid)
            if not found:
                continue
            matches, _ = matcher.match(found, list(gold))
            for m in matches:
                if m.gold_id is None:
                    continue
                union_ids.add(m.gold_id)
                runs_hitting[m.gold_id].add(rid)
                desc, rev = text_by_id.get(m.found_id, ("", ""))
                cur = best.get(m.gold_id)
                if cur is None or m.similarity_score > cur["score"]:
                    best[m.gold_id] = {
                        "score": round(float(m.similarity_score), 4),
                        "run": rid,
                        "reviewer": rev,
                        "text": desc,
                    }

        a = sum(1 for g in union_ids if id_risk.get(g) == "A")
        b = sum(1 for g in union_ids if id_risk.get(g) == "B")
        c = sum(1 for g in union_ids if id_risk.get(g) == "C")
        coverage_rows.append({
            "threshold": f"{thr:.2f}",
            "automatic_tp_candidate": len(union_ids),
            "automatic_recall_over_36": round(len(union_ids) / total_gold, 4),
            "gold_ids": " ".join(sorted(union_ids, key=int)),
            "A": a, "B": b, "C": c, "A_plus_B": a + b,
            "total_gold": total_gold,
        })

        confirmed = CONFIRMED_UBR_CBR[thr]
        for gid in sorted(union_ids, key=int):
            ctype = "existing-vs-UBR-CBR" if gid in confirmed else "new-vs-UBR-CBR"
            info = best[gid]
            candidate_rows.append({
                "threshold": f"{thr:.2f}",
                "gold_id": gid,
                "risk": id_risk.get(gid, "UNK"),
                "candidate_type": ctype,
                "n_runs_hitting": len(runs_hitting[gid]),
                "best_similarity": info["score"],
                "source_run": info["run"],
                "reviewer": info["reviewer"],
                "pbr_defect_text": info["text"][:500],
                "validation_status": "pending",
                "manual_decision": "",
                "notes": "",
            })

    OUT.mkdir(parents=True, exist_ok=True)
    COSTS.mkdir(parents=True, exist_ok=True)

    with (OUT / "pbr_automatic_coverage.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(coverage_rows[0].keys()))
        w.writeheader(); w.writerows(coverage_rows)

    with (OUT / "pbr_match_candidates.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(candidate_rows[0].keys()))
        w.writeheader(); w.writerows(candidate_rows)

    # --- cost / tokens from per-run llm_usage.csv -------------------------
    tot_in = tot_out = tot_tok = 0
    tot_cost = 0.0
    rows_seen = 0
    for rid in run_ids:
        up = RUNS / rid / "llm_usage.csv"
        if not up.exists():
            continue
        for r in csv.DictReader(up.open(encoding="utf-8")):
            rows_seen += 1
            def _i(x):
                try:
                    return int(float(x))
                except (TypeError, ValueError):
                    return 0
            def _f(x):
                try:
                    return float(x)
                except (TypeError, ValueError):
                    return 0.0
            tot_in += _i(r.get("input_tokens"))
            tot_out += _i(r.get("output_tokens"))
            tot_tok += _i(r.get("total_tokens"))
            tot_cost += _f(r.get("total_cost"))

    cov065 = coverage_rows[0]["automatic_tp_candidate"]
    cov060 = coverage_rows[1]["automatic_tp_candidate"]
    cost_per_065 = round(tot_cost / cov065, 6) if cov065 else None
    cost_per_060 = round(tot_cost / cov060, 6) if cov060 else None
    with (COSTS / "pbr_cost_summary.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["metric", "value"])
        w.writerow(["technique", "PBR"])
        w.writerow(["runs", N_RUNS])
        w.writerow(["llm_calls_logged", rows_seen])
        w.writerow(["input_tokens", tot_in])
        w.writerow(["output_tokens", tot_out])
        w.writerow(["total_tokens", tot_tok])
        w.writerow(["total_cost_usd", round(tot_cost, 6)])
        w.writerow(["currency", "USD"])
        w.writerow(["cost_per_automatic_tp_candidate_t065_usd", cost_per_065])
        w.writerow(["cost_per_automatic_tp_candidate_t060_usd", cost_per_060])
        w.writerow(["cost_per_confirmed_tp_usd", "n/a until manual validation"])

    # console summary
    print("PBR automatic coverage (CANDIDATES, pending manual validation):")
    for r in coverage_rows:
        print(f"  t={r['threshold']}: tp_candidate={r['automatic_tp_candidate']}/36 "
              f"recall={r['automatic_recall_over_36']} ids=[{r['gold_ids']}] "
              f"A={r['A']} B={r['B']} C={r['C']} A+B={r['A_plus_B']}")
    print(f"tokens total={tot_tok} (in={tot_in} out={tot_out}) cost_usd={round(tot_cost,6)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
