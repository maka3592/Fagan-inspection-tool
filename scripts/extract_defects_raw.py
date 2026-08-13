#!/usr/bin/env python3
"""Extract raw per-reviewer defects from runs/<RUN_ID>/reviewer_outputs.json.

Output: results/raw_defects_<RUN_ID>.csv (one row per (reviewer, defect)).

Defect identity is computed via the same logic used by
scripts/analyze_overlaps.py (defect_identity), so the IDs in this CSV
are directly comparable to overlap_/saturation_/unique_per_reviewer_
outputs from that script.

The gold standard is never accessed.

Usage:
    python scripts/extract_defects_raw.py --run-id <RUN_ID>
    python scripts/extract_defects_raw.py --from-log results/experiment_log.csv
    python scripts/extract_defects_raw.py --from-baseline results/baseline_manifest.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from analyze_overlaps import (  # noqa: E402  (sibling script import)
    _extract_position,
    _norm_text,
    defect_identity,
    load_reviewer_outputs,
)


CSV_COLUMNS = [
    "run_id",
    "technique",
    "n_reviewers",
    "reviewer_id",
    "defect_id",
    "fault_type",
    "position",
    "page_hint",
    "description_raw",
    "description_norm",
    "source",
    "timestamp",
]


def _read_metadata_timestamp(run_dir: Path) -> str:
    meta_path = run_dir / "metadata.json"
    if not meta_path.exists():
        return ""
    try:
        with meta_path.open("r", encoding="utf-8") as fh:
            meta = json.load(fh)
        for key in ("timestamp", "started_at", "created_at"):
            if meta.get(key):
                return str(meta[key])
    except (OSError, json.JSONDecodeError):
        pass
    return ""


def _resolve_run_meta(
    log_lookup: Dict[str, Dict[str, str]],
    run_id: str,
    reviewer_techniques: Sequence[str],
) -> Tuple[str, str]:
    """Return (technique, timestamp) from log if present, otherwise from reviewers."""
    meta = log_lookup.get(run_id, {})
    technique = meta.get("technique") or ""
    timestamp = meta.get("timestamp") or ""
    if not technique:
        techs = sorted({t for t in reviewer_techniques if t})
        technique = "+".join(techs)
    return technique, timestamp


def extract_one_run(
    run_id: str,
    runs_dir: Path,
    out_dir: Path,
    log_lookup: Dict[str, Dict[str, str]],
) -> Optional[Path]:
    run_dir = runs_dir / run_id
    rev_path = run_dir / "reviewer_outputs.json"
    if not rev_path.exists():
        print(f"[extract] WARN: {rev_path} not found, skipping", file=sys.stderr)
        return None

    reviewers = load_reviewer_outputs(rev_path)
    n_reviewers = len(reviewers)
    technique, log_ts = _resolve_run_meta(
        log_lookup,
        run_id,
        [str(r.get("technique") or "") for r in reviewers],
    )
    fallback_ts = log_ts or _read_metadata_timestamp(run_dir)

    out_path = out_dir / f"raw_defects_{run_id}.csv"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    n_rows = 0
    with out_path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=CSV_COLUMNS)
        w.writeheader()
        for idx, rev in enumerate(reviewers):
            reviewer_id = str(rev.get("reviewer_id") or f"reviewer_{idx + 1}")
            reviewer_ts = str(rev.get("timestamp") or "") or fallback_ts
            defects = rev.get("defects") or []
            for d in defects:
                if not isinstance(d, dict):
                    continue
                position = _extract_position(d)
                page_hint = d.get("page_hint") or ""
                description_raw = str(d.get("description") or "")
                w.writerow({
                    "run_id": run_id,
                    "technique": technique,
                    "n_reviewers": n_reviewers,
                    "reviewer_id": reviewer_id,
                    "defect_id": defect_identity(d),
                    "fault_type": str(d.get("fault_type") or "UNK"),
                    "position": position,
                    "page_hint": page_hint,
                    "description_raw": description_raw,
                    "description_norm": _norm_text(description_raw),
                    "source": "reviewer",
                    "timestamp": reviewer_ts,
                })
                n_rows += 1

    print(f"[extract] {run_id}: reviewers={n_reviewers} rows={n_rows} -> {out_path.name}")
    return out_path


# ---------------------------------------------------------------------------
# Run-id loading
# ---------------------------------------------------------------------------


def _load_log_lookup(log_path: Path) -> Dict[str, Dict[str, str]]:
    out: Dict[str, Dict[str, str]] = {}
    with log_path.open("r", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            rid = (row.get("run_id") or "").strip()
            if rid:
                out[rid] = row
    return out


def _iter_run_ids_from_log(log_path: Path) -> Iterable[str]:
    with log_path.open("r", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            if (row.get("run_status") or "").strip() != "ok":
                continue
            rid = (row.get("run_id") or "").strip()
            if rid:
                yield rid


def _iter_run_ids_from_baseline(manifest_path: Path) -> Iterable[str]:
    with manifest_path.open("r", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            if (row.get("status") or "").strip() != "ok":
                continue
            rid = (row.get("run_id") or "").strip()
            if rid:
                yield rid


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--run-id", help="Single run id to extract")
    g.add_argument("--from-log", help="Path to results/experiment_log.csv (only ok runs)")
    g.add_argument("--from-baseline", help="Path to results/baseline_manifest.csv (only ok rows)")
    p.add_argument("--runs-dir", default="runs", help="Directory with run subdirs (default: runs)")
    p.add_argument("--out-dir", default="results", help="Output directory (default: results)")
    p.add_argument(
        "--log",
        default="results/experiment_log.csv",
        help="Experiment log used to enrich technique/timestamp (default: results/experiment_log.csv)",
    )
    return p


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_arg_parser().parse_args(argv)
    runs_dir = Path(args.runs_dir)
    out_dir = Path(args.out_dir)

    log_lookup: Dict[str, Dict[str, str]] = {}
    log_path = Path(args.log)
    if log_path.exists():
        log_lookup = _load_log_lookup(log_path)

    if args.run_id:
        run_ids: List[str] = [args.run_id]
    elif args.from_log:
        run_ids = list(dict.fromkeys(_iter_run_ids_from_log(Path(args.from_log))))
    else:
        run_ids = list(dict.fromkeys(_iter_run_ids_from_baseline(Path(args.from_baseline))))

    if not run_ids:
        print("[extract] No run ids resolved.", file=sys.stderr)
        return 1

    n_ok = 0
    for rid in run_ids:
        if extract_one_run(rid, runs_dir, out_dir, log_lookup) is not None:
            n_ok += 1
    print(f"[extract] Done. {n_ok}/{len(run_ids)} runs extracted.")
    return 0 if n_ok > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
