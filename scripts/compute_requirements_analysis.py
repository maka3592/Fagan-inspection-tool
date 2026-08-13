#!/usr/bin/env python3
"""Reproducible derivations for the professor-feedback requirements.

Reads ONLY existing data (no new runs, no matcher changes):
- gold standard via the unmodified GoldLoader (id -> severity A/B/C)
- per-reviewer raw defects:
    results/costed_split_soft_n10/raw_defects/raw_defects_<run>.csv      (UBR/CBR)
    results/costed_pbr_split_soft_n10/raw_defects/raw_defects_<run>.csv  (PBR)
- manual-validation outcome from results/costed_split_soft_n10/final_costed_results_summary.json
- API costs from results/costed_split_soft_n10/costs/ and
  results/costed_pbr_split_soft_n10/costs/pbr_cost_summary.csv

Matching reuses the CANONICAL DefectMatcher (description_threshold=thr), exactly
as union_gold_coverage.py / fagan eval.

Outputs (written next to this run):
- results/costed_split_soft_n10/derived/validation_reproducibility.csv
- results/costed_split_soft_n10/derived/cost_effectiveness_summary.csv
- results/costed_split_soft_n10/derived/cost_effectiveness_summary.json
- results/costed_split_soft_n10/derived/reviewer_incremental_gain.csv
- results/costed_split_soft_n10/derived/merge_union_intersection_summary.csv
- results/costed_split_soft_n10/derived/pbr_supplementary_summary.csv

IMPORTANT assumption for the incremental analysis (documented in the reports):
A confirmed gold ID is "covered at reviewer budget k" if any reviewer with
index <= k (pooled across all runs of the technique) has a defect that the
canonical matcher maps to that gold ID. Reviewer index = run-internal numeric
order (reviewer_1..reviewer_10), which under split-soft scope is a section
anchor, not a random reviewer order.
"""
from __future__ import annotations
import csv, json, re, sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from fagan_tool.core.schemas import Defect, FaultType, RiskLevel  # noqa: E402
from fagan_tool.evaluation import DefectMatcher, GoldLoader  # noqa: E402

GOLD = ROOT / "artifacts/gold/Faults_List_In_ver6.xls"
MAIN = ROOT / "results/costed_split_soft_n10"
PBR = ROOT / "results/costed_pbr_split_soft_n10"
OUT = MAIN / "derived"
THRESHOLDS = [0.65, 0.60]

# Manual-validation outcome (from final_costed_results_summary.json).
SUMMARY = json.loads((MAIN / "final_costed_results_summary.json").read_text())
HVC = SUMMARY["human_validated_coverage"]
def _ids(s): return [t for t in str(s).split() if t]
CONFIRMED = {0.65: set(_ids(HVC["0.65"]["human_confirmed_gold_ids"])),
             0.60: set(_ids(HVC["0.60"]["human_confirmed_gold_ids"]))}
DOUBTFUL = {0.65: set(_ids(HVC["0.65"]["human_doubtful_gold_ids"])),
            0.60: set(_ids(HVC["0.60"]["human_doubtful_gold_ids"]))}
REJECTED = {0.65: set(_ids(HVC["0.65"]["human_rejected_gold_ids"])),
            0.60: set(_ids(HVC["0.60"]["human_rejected_gold_ids"]))}
AUTO = {0.65: set(_ids(SUMMARY["automatic_coverage"]["0.65"]["automatic_gold_ids"])),
        0.60: set(_ids(SUMMARY["automatic_coverage"]["0.60"]["automatic_gold_ids"]))}

COST = {"UBR": 0.740605, "CBR": 0.724671, "PBR": 0.639742}
COST_UBRCBR = 1.465276

gold = GoldLoader(GOLD).load()
RISK = {g.id: g.risk.value for g in gold}
TOTAL_GOLD = len(gold)


def _norm_fault(v):
    v = (v or "").strip().upper()
    return FaultType.M if v == "M" else (FaultType.W if v == "W" else FaultType.UNK)

def _row_to_defect(row):
    desc = (row.get("description_raw") or "").strip()
    return Defect(id=(row.get("defect_id") or "").strip() or f"raw_{id(row)}",
                  position=(row.get("position") or "").strip() or "unknown",
                  page_hint=(row.get("page_hint") or "").strip() or None,
                  risk=RiskLevel.UNK, fault_type=_norm_fault(row.get("fault_type")),
                  description=desc, evidence=desc, confidence=0.8,
                  reviewer_id=row.get("reviewer_id") or None)

_RIDX = re.compile(r"reviewer[_-]?(\d+)", re.I)
def _ridx(rid):
    m = _RIDX.search(rid or "")
    return int(m.group(1)) if m else 999

def load_defects(raw_dir, prefix):
    """Return list of (reviewer_index, Defect) for all runs of a technique prefix."""
    out = []
    for p in sorted(raw_dir.glob(f"raw_defects_{prefix}*.csv")):
        for row in csv.DictReader(p.open(encoding="utf-8")):
            out.append((_ridx(row.get("reviewer_id")), _row_to_defect(row)))
    return out

# matched gold ids per reviewer index, per technique, per threshold
def matched_by_reviewer(defs, thr):
    matcher = DefectMatcher(description_threshold=thr)
    by_idx = defaultdict(list)
    for ridx, d in defs:
        by_idx[ridx].append(d)
    out = {}  # reviewer_index -> set(gold_id)
    for ridx, ds in by_idx.items():
        matches, _ = matcher.match(ds, list(gold))
        out[ridx] = {m.gold_id for m in matches if m.gold_id is not None}
    return out

TECHS = {
    "UBR": load_defects(MAIN / "raw_defects", "costed_ubr_split_soft_n10"),
    "CBR": load_defects(MAIN / "raw_defects", "costed_cbr_split_soft_n10"),
    "PBR": load_defects(PBR / "raw_defects", "costed_pbr_split_soft_n10"),
}

OUT.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------- validation
with (OUT / "validation_reproducibility.csv").open("w", newline="") as fh:
    w = csv.writer(fh)
    w.writerow(["threshold", "candidate_count", "confirmed_count", "doubtful_count",
                "rejected_count", "confirmed_gold_ids", "doubtful_gold_ids",
                "rejected_gold_ids", "role", "notes"])
    for thr in THRESHOLDS:
        k = f"{thr:.2f}".rstrip("0").rstrip(".") if thr == 0.6 else f"{thr:.2f}"
        key = "0.65" if thr == 0.65 else "0.60"
        role = "main" if thr == 0.65 else "sensitivity"
        w.writerow([key, len(AUTO[thr]), len(CONFIRMED[thr]), len(DOUBTFUL[thr]),
                    len(REJECTED[thr]), " ".join(sorted(CONFIRMED[thr], key=int)),
                    " ".join(sorted(DOUBTFUL[thr], key=int)),
                    " ".join(sorted(REJECTED[thr], key=int)), role,
                    "threshold = candidate selection only; only confirmed counts as a gold hit"])

# ----------------------------------------------- per-technique confirmed sets
auto_by_tech = {}  # (tech,thr) -> set matched gold ids (pooled all reviewers)
for tech in ("UBR", "CBR", "PBR"):
    for thr in THRESHOLDS:
        mr = matched_by_reviewer(TECHS[tech], thr)
        allids = set()
        for s in mr.values():
            allids |= s
        auto_by_tech[(tech, thr)] = allids

def conf_of(tech, thr):
    """Confirmed gold ids attributable to a technique = technique's automatic
    matches intersected with the (pooled) confirmed set."""
    return auto_by_tech[(tech, thr)] & CONFIRMED[thr]

# ----------------------------------------------------- cost effectiveness
cost_rows = []
def sev_counts(ids):
    a = sum(1 for i in ids if RISK.get(i) == "A")
    b = sum(1 for i in ids if RISK.get(i) == "B")
    c = sum(1 for i in ids if RISK.get(i) == "C")
    return a, b, c

for thr in THRESHOLDS:
    role = "main" if thr == 0.65 else "sensitivity"
    conf = CONFIRMED[thr]
    nconf = len(conf)
    a, b, c = sev_counts(conf)
    # union UBR∪CBR
    cost_rows.append({
        "scope": "UBR_union_CBR", "threshold": f"{thr:.2f}", "role": role,
        "api_cost_usd": round(COST_UBRCBR, 6), "confirmed_count": nconf,
        "confirmed_ids": " ".join(sorted(conf, key=int)),
        "cost_per_confirmed_usd": round(COST_UBRCBR / nconf, 6) if nconf else "",
        "confirmed_A": a, "confirmed_B": b, "confirmed_C": c, "confirmed_A_plus_B": a + b,
        "cost_per_confirmed_A_critical_usd": round(COST_UBRCBR / a, 6) if a else "n/a",
        "cost_per_confirmed_A_plus_B_usd": round(COST_UBRCBR / (a + b), 6) if (a + b) else "n/a",
    })
    for tech in ("UBR", "CBR"):
        tc = conf_of(tech, thr)
        nt = len(tc)
        ta, tb, tcn = sev_counts(tc)
        cost_rows.append({
            "scope": tech, "threshold": f"{thr:.2f}", "role": role,
            "api_cost_usd": round(COST[tech], 6), "confirmed_count": nt,
            "confirmed_ids": " ".join(sorted(tc, key=int)),
            "cost_per_confirmed_usd": round(COST[tech] / nt, 6) if nt else "",
            "confirmed_A": ta, "confirmed_B": tb, "confirmed_C": tcn, "confirmed_A_plus_B": ta + tb,
            "cost_per_confirmed_A_critical_usd": round(COST[tech] / ta, 6) if ta else "n/a",
            "cost_per_confirmed_A_plus_B_usd": round(COST[tech] / (ta + tb), 6) if (ta + tb) else "n/a",
        })
    # supplementary union with PBR (cost adds, confirmed union unchanged unless PBR confirms new)
    pbr_conf = conf_of("PBR", thr) & CONFIRMED[thr]  # PBR auto matches that are confirmed in pooled set
    union_pbr = conf | pbr_conf
    cost_ucp = COST_UBRCBR + COST["PBR"]
    a2, b2, c2 = sev_counts(union_pbr)
    cost_rows.append({
        "scope": "UBR_union_CBR_union_PBR", "threshold": f"{thr:.2f}", "role": role,
        "api_cost_usd": round(cost_ucp, 6), "confirmed_count": len(union_pbr),
        "confirmed_ids": " ".join(sorted(union_pbr, key=int)),
        "cost_per_confirmed_usd": round(cost_ucp / len(union_pbr), 6) if union_pbr else "",
        "confirmed_A": a2, "confirmed_B": b2, "confirmed_C": c2, "confirmed_A_plus_B": a2 + b2,
        "cost_per_confirmed_A_critical_usd": round(cost_ucp / a2, 6) if a2 else "n/a",
        "cost_per_confirmed_A_plus_B_usd": round(cost_ucp / (a2 + b2), 6) if (a2 + b2) else "n/a",
    })

with (OUT / "cost_effectiveness_summary.csv").open("w", newline="") as fh:
    cols = list(cost_rows[0].keys())
    w = csv.DictWriter(fh, fieldnames=cols); w.writeheader(); w.writerows(cost_rows)

ce_json = {
    "currency": "USD",
    "basis": "list-price-based estimate on real token usage; not billing charges",
    "total_api_cost_ubr_cbr_usd": COST_UBRCBR,
    "api_cost_by_technique_usd": COST,
    "total_tokens": SUMMARY["api_usage"]["total_tokens"],
    "input_tokens": SUMMARY["api_usage"]["input_tokens"],
    "output_tokens": SUMMARY["api_usage"]["output_tokens"],
    "cached_tokens": "not available in usage logs",
    "rows": cost_rows,
    "personnel_cost_scenario_note": ("Scenario only; no controlled human inspection "
        "time was measured. NO defects-per-hour metric. Not a measured human-vs-LLM comparison."),
    "personnel_cost_scenarios_eur": SUMMARY["personnel_cost_context"]["scenarios"],
}
(OUT / "cost_effectiveness_summary.json").write_text(json.dumps(ce_json, indent=2, ensure_ascii=False))

# ----------------------------------------------- incremental reviewer budget
inc_rows = []
def cumulative_confirmed(matched_by_idx, conf):
    cum = set(); per_k = []
    for k in range(1, 11):
        cum |= matched_by_idx.get(k, set())
        per_k.append((k, set(cum & conf)))
    return per_k

for thr in THRESHOLDS:
    conf = CONFIRMED[thr]
    role = "main" if thr == 0.65 else "sensitivity"
    # per technique
    mr = {t: matched_by_reviewer(TECHS[t], thr) for t in ("UBR", "CBR")}
    # union UBR∪CBR matched per reviewer index
    mr_union = {}
    for k in range(1, 11):
        mr_union[k] = mr["UBR"].get(k, set()) | mr["CBR"].get(k, set())
    scopes = {"UBR": mr["UBR"], "CBR": mr["CBR"], "UBR_union_CBR": mr_union}
    for scope, mbi in scopes.items():
        prev = set()
        perk = cumulative_confirmed(mbi, conf)
        for k, cum in perk:
            new = cum - prev
            inc_rows.append({
                "threshold": f"{thr:.2f}", "role": role, "scope": scope,
                "reviewer_index": k,
                "cumulative_confirmed_count": len(cum),
                "cumulative_confirmed_ids": " ".join(sorted(cum, key=int)),
                "new_confirmed_added": len(new),
                "new_confirmed_ids": " ".join(sorted(new, key=int)),
                "cumulative_coverage_of_36": round(len(cum) / TOTAL_GOLD, 4),
            })
            prev = cum

with (OUT / "reviewer_incremental_gain.csv").open("w", newline="") as fh:
    cols = list(inc_rows[0].keys())
    w = csv.DictWriter(fh, fieldnames=cols); w.writeheader(); w.writerows(inc_rows)

# saturation observation: did the 10th reviewer add a confirmed id (any scope/thr)?
sat = {}
for thr in THRESHOLDS:
    for scope in ("UBR", "CBR", "UBR_union_CBR"):
        rows10 = [r for r in inc_rows if r["threshold"] == f"{thr:.2f}" and r["scope"] == scope and r["reviewer_index"] == 10]
        sat[(scope, thr)] = rows10[0]["new_confirmed_added"] if rows10 else None

# ----------------------------------------------- union / intersection (confirmed)
mi_rows = []
for thr in THRESHOLDS:
    role = "main" if thr == 0.65 else "sensitivity"
    u = conf_of("UBR", thr); c = conf_of("CBR", thr)
    p = conf_of("PBR", thr) & CONFIRMED[thr]
    sets = {
        "UBR_confirmed": u, "CBR_confirmed": c,
        "UBR_union_CBR": u | c, "UBR_intersection_CBR": u & c,
        "UBR_union_CBR_union_PBR_supplementary": u | c | p,
        "PBR_only_vs_UBR_union_CBR": p - (u | c),
    }
    for name, s in sets.items():
        mi_rows.append({"threshold": f"{thr:.2f}", "role": role, "set": name,
                        "count": len(s), "confirmed_gold_ids": " ".join(sorted(s, key=int))})

with (OUT / "merge_union_intersection_summary.csv").open("w", newline="") as fh:
    cols = list(mi_rows[0].keys())
    w = csv.DictWriter(fh, fieldnames=cols); w.writeheader(); w.writerows(mi_rows)

# ----------------------------------------------- PBR supplementary summary
pbr_rows = []
for thr in THRESHOLDS:
    role = "main" if thr == 0.65 else "sensitivity"
    auto = auto_by_tech[("PBR", thr)]
    pconf = auto & CONFIRMED[thr]
    pdoubt = auto & DOUBTFUL[thr]
    prej = auto & REJECTED[thr]
    ubrcbr = CONFIRMED[thr]
    pbr_only = pconf - ubrcbr
    pbr_rows.append({
        "threshold": f"{thr:.2f}", "role": role,
        "pbr_candidate_count": len(auto),
        "pbr_candidate_ids": " ".join(sorted(auto, key=int)),
        "pbr_confirmed_count": len(pconf), "pbr_confirmed_ids": " ".join(sorted(pconf, key=int)),
        "pbr_doubtful_ids": " ".join(sorted(pdoubt, key=int)),
        "pbr_rejected_ids": " ".join(sorted(prej, key=int)),
        "ubr_union_cbr_confirmed_ids": " ".join(sorted(ubrcbr, key=int)),
        "pbr_only_confirmed_vs_ubr_cbr": " ".join(sorted(pbr_only, key=int)) or "none",
        "delta_confirmed_from_pbr": len(pbr_only),
    })
with (OUT / "pbr_supplementary_summary.csv").open("w", newline="") as fh:
    cols = list(pbr_rows[0].keys())
    w = csv.DictWriter(fh, fieldnames=cols); w.writeheader(); w.writerows(pbr_rows)

# ----------------------------------------------- console summary
print("== VALIDATION ==")
for thr in THRESHOLDS:
    print(f"  t={thr}: candidates={len(AUTO[thr])} confirmed={len(CONFIRMED[thr])}{sorted(CONFIRMED[thr],key=int)} "
          f"doubtful={sorted(DOUBTFUL[thr],key=int)} rejected={sorted(REJECTED[thr],key=int)}")
print("== PER-TECHNIQUE CONFIRMED ==")
for thr in THRESHOLDS:
    print(f"  t={thr}: UBR={sorted(conf_of('UBR',thr),key=int)} CBR={sorted(conf_of('CBR',thr),key=int)} "
          f"inter={sorted(conf_of('UBR',thr)&conf_of('CBR',thr),key=int)}")
print("== INCREMENTAL: new confirmed added at reviewer 10 ==")
for (scope, thr), v in sat.items():
    print(f"  scope={scope} t={thr}: new_confirmed_at_r10={v}")
print("== PBR ==")
for r in pbr_rows:
    print(f"  t={r['threshold']}: confirmed={r['pbr_confirmed_ids']} pbr_only_vs_ubrcbr={r['pbr_only_confirmed_vs_ubr_cbr']} delta={r['delta_confirmed_from_pbr']}")
print("\nWrote ->", OUT)
