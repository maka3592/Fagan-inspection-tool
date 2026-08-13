#!/usr/bin/env python3
"""Reviewer-saturation analysis per run and aggregated.

For each run, this script reads
  * results/union_defects_<RUN_ID>.csv  (union_unique_total)
  * results/incremental_<RUN_ID>.csv    (cumulative curve per k)

and computes two saturation indicators:

  k95
      Smallest k such that cumulative_unique(k) >= 0.95 * union_unique_total.
      Captures *coverage* relative to the full union.

  k_plateau
      Smallest k for which the *last two* reviewers (k-1 and k) together
      contribute at most 1 new unique defect. Captures *diminishing returns*
      independent of the total. Requires k >= 2; if no such k is found,
      reported as the total reviewer count.

  k_star
      min(k95, k_plateau) — whichever criterion fires first.

Per-run output:
  results/saturation_points_per_run.csv
Aggregate by (technique, n_reviewers):
  results/saturation_points_summary.csv

Usage:
    python scripts/saturation_analysis.py --from-log results/experiment_log.csv
    python scripts/saturation_analysis.py --from-baseline results/baseline_manifest.csv

The gold standard is never accessed.
"""

from __future__ import annotations

import argparse
import csv
import math
import statistics
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple


PER_RUN_COLS = [
    "run_id", "technique", "n_reviewers", "union_unique_total",
    "k95", "k_plateau", "k_star",
    "cumulative_at_k_star", "remaining_after_k_star",
]

SUMMARY_COLS = [
    "technique", "n_reviewers", "n_runs",
    "k_star_mean", "k_star_median", "k_star_min", "k_star_max",
    "union_unique_mean", "union_unique_median",
    "remaining_mean_after_k_star",
]


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------


def _load_union_total(path: Path) -> Optional[int]:
    if not path.exists():
        return None
    n = 0
    with path.open("r", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for _ in reader:
            n += 1
    return n


def _load_incremental(path: Path) -> List[Tuple[int, int, int]]:
    """Return list of (k, new_unique, cumulative_unique) sorted by k."""
    if not path.exists():
        return []
    rows: List[Tuple[int, int, int]] = []
    with path.open("r", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            try:
                k = int(row["k"])
                new = int(row["new_unique"])
                cum = int(row["cumulative_unique"])
            except (KeyError, ValueError):
                continue
            rows.append((k, new, cum))
    rows.sort(key=lambda x: x[0])
    return rows


# ---------------------------------------------------------------------------
# Saturation criteria
# ---------------------------------------------------------------------------


def _compute_k95(curve: Sequence[Tuple[int, int, int]], union_total: int) -> Optional[int]:
    if union_total <= 0 or not curve:
        return None
    target = 0.95 * union_total
    for k, _new, cum in curve:
        if cum >= target:
            return k
    return None


def _compute_k_plateau(curve: Sequence[Tuple[int, int, int]]) -> Optional[int]:
    """Smallest k >= 2 where new_unique(k-1) + new_unique(k) <= 1."""
    if len(curve) < 2:
        return None
    for i in range(1, len(curve)):
        k_prev, new_prev, _ = curve[i - 1]
        k_curr, new_curr, _ = curve[i]
        if new_prev + new_curr <= 1:
            return k_curr
    return None


def _select_k_star(k95: Optional[int], k_plateau: Optional[int]) -> Optional[int]:
    candidates = [k for k in (k95, k_plateau) if k is not None]
    return min(candidates) if candidates else None


# ---------------------------------------------------------------------------
# Per-run driver
# ---------------------------------------------------------------------------


def _analyse_one(
    run_id: str,
    technique: str,
    n_reviewers: int,
    out_dir: Path,
) -> Optional[Dict[str, object]]:
    union_path = out_dir / f"union_defects_{run_id}.csv"
    inc_path = out_dir / f"incremental_{run_id}.csv"

    union_total = _load_union_total(union_path)
    curve = _load_incremental(inc_path)

    if union_total is None or not curve:
        print(
            f"[sat] WARN: missing inputs for {run_id} "
            f"(union_defects exists={union_path.exists()}, "
            f"incremental exists={inc_path.exists()}); skipping",
            file=sys.stderr,
        )
        return None

    k95 = _compute_k95(curve, union_total)
    k_plateau = _compute_k_plateau(curve)
    k_star = _select_k_star(k95, k_plateau)

    if k_star is not None:
        cum_at = next((cum for k, _n, cum in curve if k == k_star), curve[-1][2])
        remaining = union_total - cum_at
    else:
        cum_at = curve[-1][2]
        remaining = union_total - cum_at

    return {
        "run_id": run_id,
        "technique": technique,
        "n_reviewers": n_reviewers or len(curve),
        "union_unique_total": union_total,
        "k95": k95 if k95 is not None else "",
        "k_plateau": k_plateau if k_plateau is not None else "",
        "k_star": k_star if k_star is not None else "",
        "cumulative_at_k_star": cum_at,
        "remaining_after_k_star": remaining,
    }


# ---------------------------------------------------------------------------
# Run-id loaders (same conventions as dedupe_analysis)
# ---------------------------------------------------------------------------


def _iter_log(log_path: Path) -> Iterable[Tuple[str, str, int]]:
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


def _iter_baseline(manifest_path: Path) -> Iterable[Tuple[str, str, int]]:
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
# Writers
# ---------------------------------------------------------------------------


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
        key = (str(r["technique"]) or "", int(r["n_reviewers"]))
        buckets[key].append(r)

    rows_out: List[Dict[str, object]] = []
    for (tech, n), group in sorted(buckets.items()):
        k_stars = [int(r["k_star"]) for r in group if r["k_star"] != ""]
        uniques = [int(r["union_unique_total"]) for r in group]
        remaining = [int(r["remaining_after_k_star"]) for r in group if r["k_star"] != ""]

        def _fmt(values: Sequence[float], fn) -> str:
            return f"{fn(values):.2f}" if values else ""

        rows_out.append({
            "technique": tech,
            "n_reviewers": n,
            "n_runs": len(group),
            "k_star_mean": _fmt(k_stars, statistics.mean),
            "k_star_median": _fmt(k_stars, statistics.median),
            "k_star_min": min(k_stars) if k_stars else "",
            "k_star_max": max(k_stars) if k_stars else "",
            "union_unique_mean": _fmt(uniques, statistics.mean),
            "union_unique_median": _fmt(uniques, statistics.median),
            "remaining_mean_after_k_star": _fmt(remaining, statistics.mean),
        })

    _write_csv(out_path, rows_out, SUMMARY_COLS)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--from-log", help="Path to results/experiment_log.csv")
    g.add_argument("--from-baseline", help="Path to results/baseline_manifest.csv")
    p.add_argument("--out-dir", default="results", help="Output dir (default: results)")
    p.add_argument(
        "--per-run-out",
        default="results/saturation_points_per_run.csv",
        help="Per-run output CSV path",
    )
    p.add_argument(
        "--summary-out",
        default="results/saturation_points_summary.csv",
        help="Aggregated output CSV path",
    )
    return p


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_arg_parser().parse_args(argv)
    out_dir = Path(args.out_dir)

    if args.from_log:
        jobs = list(_iter_log(Path(args.from_log)))
    else:
        jobs = list(_iter_baseline(Path(args.from_baseline)))

    if not jobs:
        print("[sat] No runs resolved.", file=sys.stderr)
        return 1

    seen: set[str] = set()
    per_run: List[Dict[str, object]] = []
    for rid, tech, n in jobs:
        if rid in seen:
            continue
        seen.add(rid)
        row = _analyse_one(rid, tech, n, out_dir)
        if row is not None:
            per_run.append(row)

    if not per_run:
        print("[sat] No runs analysed (missing inputs).", file=sys.stderr)
        return 1

    _write_csv(Path(args.per_run_out), per_run, PER_RUN_COLS)
    _write_summary(per_run, Path(args.summary_out))
    print(f"[sat] Wrote {args.per_run_out} ({len(per_run)} rows)")
    print(f"[sat] Wrote {args.summary_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
