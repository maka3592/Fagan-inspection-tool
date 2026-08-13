#!/usr/bin/env python3
"""Overlap / unique / saturation analysis for Fagan inspection runs.

Reads ``runs/<RUN_ID>/reviewer_outputs.json`` and writes:

  * ``results/overlap_<RUN_ID>.csv``         - pairwise Jaccard reviewer matrix
  * ``results/saturation_<RUN_ID>.csv``      - k -> unique defects after k reviewers
  * ``results/unique_per_reviewer_<RUN_ID>.csv`` - per-reviewer counts (total / unique)

Batch mode (``--from-log results/experiment_log.csv``) runs the analysis for
every successful run_id in the log and additionally produces

  * ``results/summary_saturation.csv`` - aggregated (technique, n_reviewers)
    statistics over all analysed runs.

The script never touches the gold standard.

Usage:
    python scripts/analyze_overlaps.py --run-id <RUN_ID>
    python scripts/analyze_overlaps.py --from-log results/experiment_log.csv
    python scripts/analyze_overlaps.py --from-log results/experiment_log.csv \\
        --runs-dir runs --out-dir results
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import itertools
import json
import re
import statistics
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple


# ---------------------------------------------------------------------------
# Defect identity
# ---------------------------------------------------------------------------

_WS_RE = re.compile(r"\s+")
_NON_ALNUM_RE = re.compile(r"[^a-z0-9 ]+")


def _norm_text(value: Any) -> str:
    """Lowercase, strip punctuation, collapse whitespace."""
    if value is None:
        return ""
    text = str(value).lower()
    text = _NON_ALNUM_RE.sub(" ", text)
    text = _WS_RE.sub(" ", text).strip()
    return text


def _extract_position(defect: Dict[str, Any]) -> str:
    """Pick the most stable position string available."""
    for key in ("position_canonical", "position", "original_position"):
        val = defect.get(key)
        if val:
            return str(val)
    return ""


def defect_identity(defect: Dict[str, Any]) -> str:
    """Return a stable identity string for a defect.

    Preference: explicit ``defect_id`` field, otherwise a SHA1 hash over
    (fault_type, normalized description, normalized position/page_hint).
    The reviewer-local ``id`` (e.g. ``reviewer_1_ubr_c4111bbf``) is NOT used
    because it is reviewer-specific and would defeat overlap detection.
    """
    explicit = defect.get("defect_id")
    if explicit:
        return f"explicit:{explicit}"

    fault_type = str(defect.get("fault_type") or "").upper()
    description = _norm_text(defect.get("description"))
    position = _norm_text(_extract_position(defect))
    page_hint = _norm_text(defect.get("page_hint"))

    payload = "|".join([fault_type, description, position, page_hint])
    digest = hashlib.sha1(payload.encode("utf-8")).hexdigest()[:16]
    return f"h:{digest}"


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------


def load_reviewer_outputs(path: Path) -> List[Dict[str, Any]]:
    """Load reviewer outputs; tolerate list[reviewer] or {"reviewers": [...]}."""
    with path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    if isinstance(data, dict) and "reviewers" in data:
        data = data["reviewers"]
    if not isinstance(data, list):
        raise ValueError(f"Unexpected reviewer_outputs.json shape in {path}")
    return data


def reviewer_defect_sets(
    reviewers: Sequence[Dict[str, Any]],
) -> List[Tuple[str, str, Set[str]]]:
    """Return [(reviewer_id, technique, defect_id_set), ...] in input order."""
    result: List[Tuple[str, str, Set[str]]] = []
    for idx, rev in enumerate(reviewers):
        reviewer_id = str(rev.get("reviewer_id") or f"reviewer_{idx + 1}")
        technique = str(rev.get("technique") or "")
        defects = rev.get("defects") or []
        ids: Set[str] = set()
        for d in defects:
            if not isinstance(d, dict):
                continue
            ids.add(defect_identity(d))
        result.append((reviewer_id, technique, ids))
    return result


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------


def jaccard(a: Set[str], b: Set[str]) -> float:
    if not a and not b:
        return 1.0
    union = a | b
    if not union:
        return 0.0
    return len(a & b) / len(union)


def saturation_curve(
    reviewer_sets: Sequence[Tuple[str, str, Set[str]]],
) -> List[Tuple[int, str, int, int]]:
    """Return saturation rows: (k, reviewer_id_added, unique_total_after_k, new_added)."""
    rows: List[Tuple[int, str, int, int]] = []
    cumulative: Set[str] = set()
    for k, (rid, _tech, ids) in enumerate(reviewer_sets, start=1):
        before = len(cumulative)
        cumulative |= ids
        rows.append((k, rid, len(cumulative), len(cumulative) - before))
    return rows


def unique_per_reviewer(
    reviewer_sets: Sequence[Tuple[str, str, Set[str]]],
) -> List[Tuple[str, str, int, int]]:
    """Return rows: (reviewer_id, technique, n_defects, n_unique_to_this_reviewer)."""
    all_other_union: List[Set[str]] = []
    for i, (_rid, _tech, ids) in enumerate(reviewer_sets):
        others: Set[str] = set()
        for j, (_rid2, _tech2, ids2) in enumerate(reviewer_sets):
            if i == j:
                continue
            others |= ids2
        all_other_union.append(others)

    rows: List[Tuple[str, str, int, int]] = []
    for (rid, tech, ids), others in zip(reviewer_sets, all_other_union):
        unique = ids - others
        rows.append((rid, tech, len(ids), len(unique)))
    return rows


# ---------------------------------------------------------------------------
# CSV writers
# ---------------------------------------------------------------------------


def write_overlap_matrix(
    reviewer_sets: Sequence[Tuple[str, str, Set[str]]],
    out_path: Path,
) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    ids = [r[0] for r in reviewer_sets]
    with out_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["reviewer_id", *ids])
        for (rid_a, _ta, set_a) in reviewer_sets:
            row = [rid_a]
            for (_rid_b, _tb, set_b) in reviewer_sets:
                row.append(f"{jaccard(set_a, set_b):.4f}")
            writer.writerow(row)


def write_saturation(
    rows: Sequence[Tuple[int, str, int, int]],
    out_path: Path,
) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["k", "reviewer_id_added", "unique_defects_after_k", "new_defects_added"])
        for k, rid, total, added in rows:
            writer.writerow([k, rid, total, added])


def write_unique_per_reviewer(
    rows: Sequence[Tuple[str, str, int, int]],
    out_path: Path,
) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["reviewer_id", "technique", "n_defects", "n_unique_to_reviewer"])
        for rid, tech, n, unique in rows:
            writer.writerow([rid, tech, n, unique])


# ---------------------------------------------------------------------------
# Per-run driver
# ---------------------------------------------------------------------------


def analyze_run(
    run_id: str,
    runs_dir: Path,
    out_dir: Path,
) -> Optional[Dict[str, Any]]:
    """Analyse a single run; return summary dict or None on failure."""
    run_path = runs_dir / run_id / "reviewer_outputs.json"
    if not run_path.exists():
        print(f"[analyze] WARN: {run_path} not found, skipping", file=sys.stderr)
        return None

    reviewers = load_reviewer_outputs(run_path)
    reviewer_sets = reviewer_defect_sets(reviewers)
    n_reviewers = len(reviewer_sets)

    overlap_path = out_dir / f"overlap_{run_id}.csv"
    saturation_path = out_dir / f"saturation_{run_id}.csv"
    unique_path = out_dir / f"unique_per_reviewer_{run_id}.csv"

    write_overlap_matrix(reviewer_sets, overlap_path)
    sat_rows = saturation_curve(reviewer_sets)
    write_saturation(sat_rows, saturation_path)
    uniq_rows = unique_per_reviewer(reviewer_sets)
    write_unique_per_reviewer(uniq_rows, unique_path)

    pairwise = []
    for (rid_a, _ta, sa), (rid_b, _tb, sb) in itertools.combinations(reviewer_sets, 2):
        pairwise.append(jaccard(sa, sb))
    mean_pairwise = statistics.mean(pairwise) if pairwise else float("nan")

    total_unique = sat_rows[-1][2] if sat_rows else 0
    techniques = sorted({tech for _rid, tech, _ids in reviewer_sets if tech})
    technique_str = "+".join(techniques) if techniques else ""

    print(
        f"[analyze] {run_id}: reviewers={n_reviewers} "
        f"unique_total={total_unique} mean_jaccard={mean_pairwise:.3f} "
        f"-> {overlap_path.name}, {saturation_path.name}"
    )

    return {
        "run_id": run_id,
        "technique": technique_str,
        "n_reviewers": n_reviewers,
        "unique_defects_total": total_unique,
        "mean_pairwise_jaccard": mean_pairwise,
        "per_reviewer_defect_counts": [n for _rid, _tech, n, _u in uniq_rows],
    }


# ---------------------------------------------------------------------------
# Batch driver
# ---------------------------------------------------------------------------


def iter_run_ids_from_log(log_path: Path) -> Iterable[Tuple[str, str, str, int]]:
    """Yield (run_id, technique, scope_mode, n_reviewers) from experiment_log.csv.

    Only rows whose run_status == "ok" are returned; eval status is ignored
    because reviewer_outputs.json exists regardless of eval success.
    """
    with log_path.open("r", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            if (row.get("run_status") or "").strip() != "ok":
                continue
            try:
                n = int(row.get("n_reviewers") or "0")
            except ValueError:
                n = 0
            yield (
                (row.get("run_id") or "").strip(),
                (row.get("technique") or "").strip(),
                (row.get("scope_mode") or "").strip(),
                n,
            )


def write_summary_saturation(
    summaries: Sequence[Dict[str, Any]],
    out_path: Path,
    log_lookup: Dict[str, Tuple[str, str, int]],
) -> None:
    """Aggregate per (technique, n_reviewers, scope_mode) over multiple runs."""
    buckets: Dict[Tuple[str, str, int], List[int]] = {}
    for s in summaries:
        run_id = s["run_id"]
        meta = log_lookup.get(run_id)
        if meta is not None:
            tech, scope, n_log = meta
            n = n_log or s["n_reviewers"]
        else:
            tech = s["technique"]
            scope = ""
            n = s["n_reviewers"]
        key = (tech or "", scope or "", n)
        buckets.setdefault(key, []).append(int(s["unique_defects_total"]))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow([
            "technique", "scope_mode", "n_reviewers", "n_runs",
            "unique_defects_mean", "unique_defects_median",
            "unique_defects_min", "unique_defects_max",
        ])
        for (tech, scope, n), values in sorted(buckets.items()):
            mean = statistics.mean(values) if values else 0.0
            median = statistics.median(values) if values else 0.0
            writer.writerow([
                tech, scope, n, len(values),
                f"{mean:.2f}", f"{median:.2f}",
                min(values) if values else 0,
                max(values) if values else 0,
            ])


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--run-id", help="Single run id to analyse")
    parser.add_argument(
        "--from-log",
        help="Batch mode: path to results/experiment_log.csv",
    )
    parser.add_argument(
        "--runs-dir",
        default="runs",
        help="Directory holding run subdirectories (default: runs)",
    )
    parser.add_argument(
        "--out-dir",
        default="results",
        help="Directory to write analysis CSVs (default: results)",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    runs_dir = Path(args.runs_dir)
    out_dir = Path(args.out_dir)

    if not args.run_id and not args.from_log:
        parser.error("either --run-id or --from-log must be provided")

    summaries: List[Dict[str, Any]] = []
    log_lookup: Dict[str, Tuple[str, str, int]] = {}

    if args.run_id:
        summary = analyze_run(args.run_id, runs_dir, out_dir)
        if summary is not None:
            summaries.append(summary)

    if args.from_log:
        log_path = Path(args.from_log)
        if not log_path.exists():
            print(f"[analyze] ERROR: log not found: {log_path}", file=sys.stderr)
            return 2
        seen: Set[str] = set()
        for run_id, tech, scope, n_rev in iter_run_ids_from_log(log_path):
            if not run_id or run_id in seen:
                continue
            seen.add(run_id)
            log_lookup[run_id] = (tech, scope, n_rev)
            summary = analyze_run(run_id, runs_dir, out_dir)
            if summary is not None:
                summaries.append(summary)

        if summaries:
            summary_path = out_dir / "summary_saturation.csv"
            write_summary_saturation(summaries, summary_path, log_lookup)
            print(f"[analyze] Wrote {summary_path}")

    if not summaries:
        print("[analyze] No runs analysed.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
