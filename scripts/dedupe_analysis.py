#!/usr/bin/env python3
"""Dedupe analysis for Fagan inspection runs (no gold access).

Per RUN_ID, reads runs/<RUN_ID>/reviewer_outputs.json and produces:

  * results/per_reviewer_dedupe_<RUN_ID>.csv
      reviewer_id, total_findings, unique_ids, duplicates, duplicate_ratio
      (within-reviewer dedupe stats)

  * results/union_defects_<RUN_ID>.csv
      run_id, defect_id, reviewer_count, reviewer_ids,
      representative_fault_type, representative_position,
      representative_page_hint, representative_description
      (one row per distinct defect_id across the run; reviewer_count = how
      many reviewers reported it)

  * results/incremental_<RUN_ID>.csv
      k, reviewer_id, new_unique, cumulative_unique
      (reviewers processed in stable lexical order of reviewer_id)

Batch mode (--from-log or --from-baseline) additionally writes:

  * results/defect_frequency_summary.csv
      group_by (technique, n_reviewers):
        n_runs, union_unique_mean/median, duplicate_ratio_mean,
        top_defect_ids (top by reviewer-frequency across the group)

The pairwise reviewer Jaccard matrix is NOT regenerated here because
scripts/analyze_overlaps.py already writes results/overlap_<RUN_ID>.csv
with the same defect_id semantics.

Usage:
    python scripts/dedupe_analysis.py --run-id <RUN_ID>
    python scripts/dedupe_analysis.py --from-log results/experiment_log.csv
    python scripts/dedupe_analysis.py --from-baseline results/baseline_manifest.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import statistics
import sys
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

_REVIEWER_NUM_RE = re.compile(r"reviewer[_-]?(\d+)", re.IGNORECASE)


def _reviewer_sort_key(reviewer_id: str) -> Tuple[int, int, str]:
    """Sort reviewers numerically by trailing index; fallback lexical."""
    m = _REVIEWER_NUM_RE.search(reviewer_id)
    if m:
        return (0, int(m.group(1)), reviewer_id)
    return (1, 0, reviewer_id)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from analyze_overlaps import (  # noqa: E402  (sibling script import)
    _extract_position,
    defect_identity,
    load_reviewer_outputs,
)


# ---------------------------------------------------------------------------
# Per-run analysis
# ---------------------------------------------------------------------------


def _per_reviewer_dedupe(
    reviewers: Sequence[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for idx, rev in enumerate(reviewers):
        rid = str(rev.get("reviewer_id") or f"reviewer_{idx + 1}")
        defects = [d for d in (rev.get("defects") or []) if isinstance(d, dict)]
        ids = [defect_identity(d) for d in defects]
        total = len(ids)
        uniq = len(set(ids))
        dup = total - uniq
        ratio = (dup / total) if total else 0.0
        rows.append({
            "reviewer_id": rid,
            "total_findings": total,
            "unique_ids": uniq,
            "duplicates": dup,
            "duplicate_ratio": ratio,
        })
    return rows


def _build_union(
    reviewers: Sequence[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Group defects by defect_id; return one row per distinct id.

    Reviewer count is the number of DISTINCT reviewers that reported the id.
    The representative fields come from the first occurrence (stable across
    reruns because reviewer order in the JSON is fixed).
    """
    by_id: Dict[str, Dict[str, Any]] = {}
    reviewers_by_id: Dict[str, Set[str]] = defaultdict(set)

    for idx, rev in enumerate(reviewers):
        rid = str(rev.get("reviewer_id") or f"reviewer_{idx + 1}")
        for d in rev.get("defects") or []:
            if not isinstance(d, dict):
                continue
            did = defect_identity(d)
            reviewers_by_id[did].add(rid)
            if did not in by_id:
                by_id[did] = {
                    "defect_id": did,
                    "representative_fault_type": str(d.get("fault_type") or "UNK"),
                    "representative_position": _extract_position(d),
                    "representative_page_hint": str(d.get("page_hint") or ""),
                    "representative_description": str(d.get("description") or ""),
                }

    rows: List[Dict[str, Any]] = []
    for did, base in by_id.items():
        rev_ids = sorted(reviewers_by_id[did])
        row = dict(base)
        row["reviewer_count"] = len(rev_ids)
        row["reviewer_ids"] = ";".join(rev_ids)
        rows.append(row)
    rows.sort(key=lambda r: (-r["reviewer_count"], r["defect_id"]))
    return rows


def _incremental_curve(
    reviewers: Sequence[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Sort reviewers numerically by trailing index (reviewer_1..reviewer_10)
    and report new vs. cumulative defect ids when each is added in turn.
    """
    enriched: List[Tuple[str, Set[str]]] = []
    for idx, rev in enumerate(reviewers):
        rid = str(rev.get("reviewer_id") or f"reviewer_{idx + 1}")
        ids = {defect_identity(d) for d in (rev.get("defects") or []) if isinstance(d, dict)}
        enriched.append((rid, ids))
    enriched.sort(key=lambda x: _reviewer_sort_key(x[0]))

    rows: List[Dict[str, Any]] = []
    cumulative: Set[str] = set()
    for k, (rid, ids) in enumerate(enriched, start=1):
        before = len(cumulative)
        cumulative |= ids
        rows.append({
            "k": k,
            "reviewer_id": rid,
            "new_unique": len(cumulative) - before,
            "cumulative_unique": len(cumulative),
        })
    return rows


# ---------------------------------------------------------------------------
# CSV writers
# ---------------------------------------------------------------------------


def _write_csv(path: Path, rows: Sequence[Dict[str, Any]], cols: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(cols))
        w.writeheader()
        for r in rows:
            out = {}
            for c in cols:
                val = r.get(c, "")
                if isinstance(val, float):
                    out[c] = f"{val:.4f}"
                else:
                    out[c] = val
            w.writerow(out)


PER_REV_COLS = ["reviewer_id", "total_findings", "unique_ids", "duplicates", "duplicate_ratio"]
UNION_COLS = [
    "run_id", "defect_id", "reviewer_count", "reviewer_ids",
    "representative_fault_type", "representative_position",
    "representative_page_hint", "representative_description",
]
INC_COLS = ["k", "reviewer_id", "new_unique", "cumulative_unique"]


# ---------------------------------------------------------------------------
# Per-run driver
# ---------------------------------------------------------------------------


def analyse_run(
    run_id: str,
    runs_dir: Path,
    out_dir: Path,
) -> Optional[Dict[str, Any]]:
    run_path = runs_dir / run_id / "reviewer_outputs.json"
    if not run_path.exists():
        print(f"[dedupe] WARN: {run_path} not found, skipping", file=sys.stderr)
        return None

    reviewers = load_reviewer_outputs(run_path)
    per_rev = _per_reviewer_dedupe(reviewers)
    union_rows = _build_union(reviewers)
    for r in union_rows:
        r["run_id"] = run_id
    inc_rows = _incremental_curve(reviewers)

    _write_csv(out_dir / f"per_reviewer_dedupe_{run_id}.csv", per_rev, PER_REV_COLS)
    _write_csv(out_dir / f"union_defects_{run_id}.csv", union_rows, UNION_COLS)
    _write_csv(out_dir / f"incremental_{run_id}.csv", inc_rows, INC_COLS)

    union_unique = len(union_rows)
    n_rev = len(reviewers)
    mean_dup_ratio = (
        statistics.mean(r["duplicate_ratio"] for r in per_rev) if per_rev else 0.0
    )
    print(
        f"[dedupe] {run_id}: reviewers={n_rev} "
        f"union_unique={union_unique} mean_dup_ratio={mean_dup_ratio:.3f} "
        f"-> per_reviewer_dedupe_, union_defects_, incremental_"
    )

    # Frequency contribution: how often each defect_id appeared (by reviewer
    # count), used for the batch top-k aggregation.
    freq: Counter[str] = Counter()
    for r in union_rows:
        freq[r["defect_id"]] += int(r["reviewer_count"])

    return {
        "run_id": run_id,
        "n_reviewers": n_rev,
        "union_unique": union_unique,
        "mean_duplicate_ratio": mean_dup_ratio,
        "defect_id_frequency": freq,
    }


# ---------------------------------------------------------------------------
# Run-id loading (same conventions as extract_defects_raw)
# ---------------------------------------------------------------------------


def _load_log_lookup(log_path: Path) -> Dict[str, Dict[str, str]]:
    out: Dict[str, Dict[str, str]] = {}
    if not log_path.exists():
        return out
    with log_path.open("r", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            rid = (row.get("run_id") or "").strip()
            if rid:
                out[rid] = row
    return out


def _iter_run_ids_from_log(log_path: Path) -> Iterable[Tuple[str, str, int]]:
    with log_path.open("r", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            if (row.get("run_status") or "").strip() != "ok":
                continue
            rid = (row.get("run_id") or "").strip()
            if not rid:
                continue
            try:
                n = int(row.get("n_reviewers") or "0")
            except ValueError:
                n = 0
            yield rid, (row.get("technique") or "").strip(), n


def _iter_run_ids_from_baseline(manifest_path: Path) -> Iterable[Tuple[str, str, int]]:
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
            yield rid, (row.get("technique") or "").strip(), n


# ---------------------------------------------------------------------------
# Batch summary
# ---------------------------------------------------------------------------


SUMMARY_COLS = [
    "technique", "n_reviewers", "n_runs",
    "union_unique_mean", "union_unique_median",
    "union_unique_min", "union_unique_max",
    "duplicate_ratio_mean",
    "top_defect_ids",
]


def _write_summary(
    summaries: Sequence[Dict[str, Any]],
    meta_by_run: Dict[str, Tuple[str, int]],
    out_path: Path,
    top_k: int = 5,
) -> None:
    buckets: Dict[Tuple[str, int], List[Dict[str, Any]]] = defaultdict(list)
    freq_by_bucket: Dict[Tuple[str, int], Counter[str]] = defaultdict(Counter)

    for s in summaries:
        tech, n_log = meta_by_run.get(s["run_id"], ("", s["n_reviewers"]))
        key = (tech or "", n_log or s["n_reviewers"])
        buckets[key].append(s)
        freq_by_bucket[key].update(s["defect_id_frequency"])

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=SUMMARY_COLS)
        w.writeheader()
        for key in sorted(buckets):
            tech, n = key
            grp = buckets[key]
            uniques = [g["union_unique"] for g in grp]
            ratios = [g["mean_duplicate_ratio"] for g in grp]
            top = freq_by_bucket[key].most_common(top_k)
            w.writerow({
                "technique": tech,
                "n_reviewers": n,
                "n_runs": len(grp),
                "union_unique_mean": f"{statistics.mean(uniques):.2f}" if uniques else "0",
                "union_unique_median": f"{statistics.median(uniques):.2f}" if uniques else "0",
                "union_unique_min": min(uniques) if uniques else 0,
                "union_unique_max": max(uniques) if uniques else 0,
                "duplicate_ratio_mean": f"{statistics.mean(ratios):.4f}" if ratios else "0",
                "top_defect_ids": ";".join(f"{did}:{cnt}" for did, cnt in top),
            })


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--run-id", help="Single run id to analyse")
    g.add_argument("--from-log", help="Path to results/experiment_log.csv (only ok runs)")
    g.add_argument("--from-baseline", help="Path to results/baseline_manifest.csv (only ok rows)")
    p.add_argument("--runs-dir", default="runs", help="Run subdirs (default: runs)")
    p.add_argument("--out-dir", default="results", help="Output dir (default: results)")
    p.add_argument(
        "--log",
        default="results/experiment_log.csv",
        help="Log used to attach technique/n_reviewers when grouping (default: results/experiment_log.csv)",
    )
    p.add_argument("--top-k", type=int, default=5, help="Top-k defect_ids in summary (default: 5)")
    return p


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_arg_parser().parse_args(argv)
    runs_dir = Path(args.runs_dir)
    out_dir = Path(args.out_dir)

    log_lookup = _load_log_lookup(Path(args.log))

    if args.run_id:
        run_jobs: List[Tuple[str, str, int]] = []
        meta = log_lookup.get(args.run_id, {})
        try:
            n = int(meta.get("n_reviewers") or "0")
        except ValueError:
            n = 0
        run_jobs.append((args.run_id, meta.get("technique") or "", n))
    elif args.from_log:
        run_jobs = list(_iter_run_ids_from_log(Path(args.from_log)))
    else:
        run_jobs = list(_iter_run_ids_from_baseline(Path(args.from_baseline)))

    if not run_jobs:
        print("[dedupe] No run ids resolved.", file=sys.stderr)
        return 1

    seen: Set[str] = set()
    summaries: List[Dict[str, Any]] = []
    meta_by_run: Dict[str, Tuple[str, int]] = {}
    for rid, tech, n in run_jobs:
        if rid in seen:
            continue
        seen.add(rid)
        meta_by_run[rid] = (tech, n)
        result = analyse_run(rid, runs_dir, out_dir)
        if result is not None:
            summaries.append(result)

    if (args.from_log or args.from_baseline) and summaries:
        out_path = out_dir / "defect_frequency_summary.csv"
        _write_summary(summaries, meta_by_run, out_path, top_k=args.top_k)
        print(f"[dedupe] Wrote {out_path}")

    print(f"[dedupe] Done. {len(summaries)}/{len(seen)} runs analysed.")
    return 0 if summaries else 1


if __name__ == "__main__":
    raise SystemExit(main())
