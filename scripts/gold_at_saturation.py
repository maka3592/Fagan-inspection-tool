#!/usr/bin/env python3
"""Gold-Nutzen am Sättigungspunkt: evaluate Union@k_star against gold standard.

For each run in the baseline manifest, this script:
  1. Reads k_star from results/saturation_points_per_run.csv.
  2. Picks reviewers 1..k_star from results/raw_defects_<RUN_ID>.csv
     (reviewers are sorted numerically by the integer in their reviewer_id).
  3. Builds the union of defects over defect_id (first occurrence wins).
  4. Matches the union against the gold standard using the same matcher
     as ``fagan eval`` (DefectMatcher with description_threshold = --threshold).
  5. Computes TP/FP/FN, Precision/Recall/F1, and Recall split by Risk A/B.

Outputs:
  results/gold_at_saturation_per_run.csv
  results/gold_at_saturation_summary.csv (aggregated by technique, n_reviewers)

The gold standard is only read by the evaluation module (LeakageGuard
applies to agent code, not evaluation scripts). No new inspection runs are
started.
"""

from __future__ import annotations

import argparse
import csv
import re
import statistics
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

# Make the project's src/ importable so we can reuse the canonical matcher.
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_SRC_DIR = _PROJECT_ROOT / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from fagan_tool.core.schemas import (  # noqa: E402
    Defect,
    FaultType,
    GoldDefect,
    MatchType,
    RiskLevel,
)
from fagan_tool.evaluation import DefectMatcher, GoldLoader  # noqa: E402


PER_RUN_COLS = [
    "run_id", "technique", "n_reviewers", "k_star", "threshold",
    "tp", "fp", "fn", "precision", "recall", "f1",
    "recall_A", "recall_B",
]

SUMMARY_COLS = [
    "technique", "n_reviewers", "n_runs",
    "k_star_mean",
    "tp_mean", "fp_mean", "fn_mean",
    "precision_mean", "recall_mean", "f1_mean",
    "recall_A_mean", "recall_B_mean",
]


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------


def _load_baseline(manifest_path: Path) -> List[Tuple[str, str, int]]:
    """Return list of (run_id, technique, n_reviewers) for status == 'ok'."""
    if not manifest_path.exists():
        raise FileNotFoundError(f"Baseline manifest not found: {manifest_path}")
    out: List[Tuple[str, str, int]] = []
    with manifest_path.open("r", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            if (row.get("status") or "").strip() != "ok":
                continue
            rid = (row.get("run_id") or "").strip()
            if not rid:
                continue
            try:
                n = int(row.get("n_reviewers") or "0")
            except ValueError:
                n = 0
            out.append((rid, (row.get("technique") or "").strip(), n))
    return out


def _load_k_star(saturation_path: Path) -> Dict[str, int]:
    """Return {run_id: k_star} for runs where k_star is present."""
    if not saturation_path.exists():
        raise FileNotFoundError(f"Saturation file not found: {saturation_path}")
    out: Dict[str, int] = {}
    with saturation_path.open("r", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            rid = (row.get("run_id") or "").strip()
            ks_raw = (row.get("k_star") or "").strip()
            if not rid or not ks_raw:
                continue
            try:
                out[rid] = int(ks_raw)
            except ValueError:
                continue
    return out


_REVIEWER_NUM_RE = re.compile(r"reviewer[_-]?(\d+)", re.IGNORECASE)


def _reviewer_index(reviewer_id: str) -> int:
    """Extract the numeric index from a reviewer_id like 'reviewer_3_ubr'."""
    m = _REVIEWER_NUM_RE.search(reviewer_id or "")
    return int(m.group(1)) if m else 10**9  # unknown reviewers go last


def _load_raw_defects(path: Path) -> List[Dict[str, str]]:
    """Return rows from raw_defects_<RUN_ID>.csv (no schema coercion)."""
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


# ---------------------------------------------------------------------------
# Union@k_star + Defect construction
# ---------------------------------------------------------------------------


def _normalize_fault_type(value: str) -> FaultType:
    v = (value or "").strip().upper()
    if v == "M":
        return FaultType.M
    if v == "W":
        return FaultType.W
    return FaultType.UNK


def union_at_k_star(
    rows: Sequence[Dict[str, str]],
    k_star: int,
) -> List[Defect]:
    """Union defects from reviewers 1..k_star, keyed by defect_id.

    Reviewers are ordered by the numeric index embedded in reviewer_id.
    Within the selected reviewer set, the first occurrence of each
    defect_id is taken as the representative row.
    """
    if k_star <= 0 or not rows:
        return []

    reviewers_sorted = sorted(
        {(r.get("reviewer_id") or "") for r in rows},
        key=_reviewer_index,
    )
    selected = set(reviewers_sorted[:k_star])

    seen: Dict[str, Dict[str, str]] = {}
    for r in rows:
        if (r.get("reviewer_id") or "") not in selected:
            continue
        did = (r.get("defect_id") or "").strip()
        if not did or did in seen:
            continue
        seen[did] = r

    defects: List[Defect] = []
    for did, r in seen.items():
        description = (r.get("description_raw") or "").strip()
        position = (r.get("position") or "").strip() or "unknown"
        page_hint = (r.get("page_hint") or "").strip() or None
        # Evidence is required by the Defect schema. The raw CSV does not
        # carry a separate evidence field, so we reuse the description as
        # a paraphrase — that is what the matcher reads anyway.
        defects.append(
            Defect(
                id=did,
                position=position,
                page_hint=page_hint,
                risk=RiskLevel.UNK,
                fault_type=_normalize_fault_type(r.get("fault_type") or ""),
                description=description,
                evidence=description,
                confidence=0.8,
                reviewer_id=r.get("reviewer_id") or None,
            )
        )
    return defects


# ---------------------------------------------------------------------------
# Metric computation (TP/FP/FN + Recall by Risk)
# ---------------------------------------------------------------------------


def _safe_div(num: float, den: float) -> float:
    return num / den if den > 0 else 0.0


def evaluate_union(
    found: Sequence[Defect],
    gold: Sequence[GoldDefect],
    threshold: float,
) -> Dict[str, float]:
    """Match found vs gold and return TP/FP/FN/precision/recall/f1 + risk recall.

    Uses the same one-to-one greedy matcher as ``fagan eval`` with
    description_threshold = threshold. TP = matches with type EXACT/PARTIAL,
    FP = all other found defects (including potential-new and duplicates),
    FN = gold defects without a matched found defect.
    """
    matcher = DefectMatcher(description_threshold=threshold)
    matches, _stats = matcher.match(list(found), list(gold))

    tp_match_types = {MatchType.EXACT, MatchType.PARTIAL}
    matched_gold_ids = {
        m.gold_id for m in matches if m.match_type in tp_match_types and m.gold_id
    }
    tp = len(matched_gold_ids)
    # Match ``fagan eval`` accounting: duplicates are not counted as FPs.
    duplicates = sum(1 for m in matches if m.match_type == MatchType.DUPLICATE)
    fp = max(0, len(found) - tp - duplicates)
    fn = len(gold) - tp

    precision = _safe_div(tp, tp + fp)
    recall = _safe_div(tp, len(gold))
    f1 = _safe_div(2 * precision * recall, precision + recall)

    # Recall by risk level (A and B = critical defects)
    def _recall_for(level: RiskLevel) -> float:
        total = sum(1 for g in gold if g.risk == level)
        if total == 0:
            return 0.0
        matched = sum(
            1 for g in gold if g.risk == level and g.id in matched_gold_ids
        )
        return matched / total

    return {
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "recall_A": _recall_for(RiskLevel.A),
        "recall_B": _recall_for(RiskLevel.B),
    }


# ---------------------------------------------------------------------------
# Writers
# ---------------------------------------------------------------------------


def _fmt(value: float, digits: int = 4) -> str:
    return f"{value:.{digits}f}"


def _write_csv(path: Path, rows: Sequence[Dict[str, object]], cols: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(cols))
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in cols})


def _write_summary(per_run: Sequence[Dict[str, object]], out_path: Path) -> None:
    buckets: Dict[Tuple[str, int], List[Dict[str, object]]] = defaultdict(list)
    for r in per_run:
        tech = str(r.get("technique") or "")
        try:
            n = int(r.get("n_reviewers") or 0)
        except (TypeError, ValueError):
            n = 0
        buckets[(tech, n)].append(r)

    def _mean(values: Sequence[float]) -> str:
        return _fmt(statistics.mean(values)) if values else ""

    rows_out: List[Dict[str, object]] = []
    for (tech, n), group in sorted(buckets.items()):
        k_stars = [float(r["k_star"]) for r in group if r["k_star"] != ""]
        tp_vals = [float(r["tp"]) for r in group]
        fp_vals = [float(r["fp"]) for r in group]
        fn_vals = [float(r["fn"]) for r in group]
        prec = [float(r["precision"]) for r in group]
        rec = [float(r["recall"]) for r in group]
        f1 = [float(r["f1"]) for r in group]
        rec_a = [float(r["recall_A"]) for r in group]
        rec_b = [float(r["recall_B"]) for r in group]

        rows_out.append({
            "technique": tech,
            "n_reviewers": n,
            "n_runs": len(group),
            "k_star_mean": _mean(k_stars),
            "tp_mean": _fmt(statistics.mean(tp_vals), 2) if tp_vals else "",
            "fp_mean": _fmt(statistics.mean(fp_vals), 2) if fp_vals else "",
            "fn_mean": _fmt(statistics.mean(fn_vals), 2) if fn_vals else "",
            "precision_mean": _mean(prec),
            "recall_mean": _mean(rec),
            "f1_mean": _mean(f1),
            "recall_A_mean": _mean(rec_a),
            "recall_B_mean": _mean(rec_b),
        })

    _write_csv(out_path, rows_out, SUMMARY_COLS)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument(
        "--from-baseline",
        required=True,
        help="Path to results/baseline_manifest.csv",
    )
    p.add_argument(
        "--gold",
        required=True,
        help="Path to artifacts/gold/Faults_List_In_ver6.xls",
    )
    p.add_argument(
        "--threshold",
        type=float,
        default=0.65,
        help="Description-similarity threshold for the matcher (default: 0.65)",
    )
    p.add_argument(
        "--results-dir",
        default="results",
        help="Directory holding raw_defects_*.csv and saturation_points_per_run.csv",
    )
    p.add_argument(
        "--saturation-file",
        default=None,
        help="Override path to saturation_points_per_run.csv (default: <results-dir>/saturation_points_per_run.csv)",
    )
    p.add_argument(
        "--per-run-out",
        default=None,
        help="Per-run output CSV (default: <results-dir>/gold_at_saturation_per_run.csv)",
    )
    p.add_argument(
        "--summary-out",
        default=None,
        help="Summary CSV (default: <results-dir>/gold_at_saturation_summary.csv)",
    )
    return p


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_arg_parser().parse_args(argv)
    results_dir = Path(args.results_dir)
    saturation_path = Path(args.saturation_file) if args.saturation_file else results_dir / "saturation_points_per_run.csv"
    per_run_out = Path(args.per_run_out) if args.per_run_out else results_dir / "gold_at_saturation_per_run.csv"
    summary_out = Path(args.summary_out) if args.summary_out else results_dir / "gold_at_saturation_summary.csv"

    # Load inputs
    jobs = _load_baseline(Path(args.from_baseline))
    if not jobs:
        print("[gold@sat] No runs in baseline manifest.", file=sys.stderr)
        return 1

    k_star_map = _load_k_star(saturation_path)
    if not k_star_map:
        print(f"[gold@sat] No k_star values found in {saturation_path}.", file=sys.stderr)
        return 1

    print(f"[gold@sat] Loading gold standard from {args.gold} ...")
    gold = GoldLoader(args.gold).load()
    print(f"[gold@sat]   gold defects: {len(gold)}")
    risk_count = {r.value: sum(1 for g in gold if g.risk == r) for r in RiskLevel}
    print(f"[gold@sat]   by risk: {risk_count}")
    print(f"[gold@sat] Matching threshold: {args.threshold}")

    per_run: List[Dict[str, object]] = []
    skipped: List[str] = []

    for run_id, technique, n_reviewers in jobs:
        if run_id not in k_star_map:
            skipped.append(f"{run_id} (no k_star)")
            continue
        k_star = k_star_map[run_id]
        raw_path = results_dir / f"raw_defects_{run_id}.csv"
        rows = _load_raw_defects(raw_path)
        if not rows:
            skipped.append(f"{run_id} (no raw defects at {raw_path})")
            continue

        found = union_at_k_star(rows, k_star)
        metrics = evaluate_union(found, gold, threshold=args.threshold)

        per_run.append({
            "run_id": run_id,
            "technique": technique,
            "n_reviewers": n_reviewers,
            "k_star": k_star,
            "threshold": args.threshold,
            "tp": metrics["tp"],
            "fp": metrics["fp"],
            "fn": metrics["fn"],
            "precision": _fmt(metrics["precision"]),
            "recall": _fmt(metrics["recall"]),
            "f1": _fmt(metrics["f1"]),
            "recall_A": _fmt(metrics["recall_A"]),
            "recall_B": _fmt(metrics["recall_B"]),
        })

    if skipped:
        print(f"[gold@sat] Skipped {len(skipped)} run(s):", file=sys.stderr)
        for s in skipped:
            print(f"  - {s}", file=sys.stderr)

    if not per_run:
        print("[gold@sat] No runs evaluated.", file=sys.stderr)
        return 1

    _write_csv(per_run_out, per_run, PER_RUN_COLS)
    _write_summary(per_run, summary_out)
    print(f"[gold@sat] Wrote {per_run_out} ({len(per_run)} rows)")
    print(f"[gold@sat] Wrote {summary_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
