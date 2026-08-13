#!/usr/bin/env python3
"""Gold coverage for UBR, CBR, PBR, and their union (UBR ∪ CBR ∪ PBR).

For each selected run we

  1. Read ``results/raw_defects_<RUN_ID>.csv``.
  2. Match each reviewer's raw defects against the gold standard via the
     same ``DefectMatcher`` used by ``fagan eval``
     (``description_threshold = --threshold``).
  3. Take the per-reviewer set of matched gold IDs.
  4. Form the per-run set as the union across that run's reviewers.

Across all selected runs of a technique we pool those sets and compare

    G_UBR, G_CBR, G_PBR, G_UNION = G_UBR ∪ G_CBR ∪ G_PBR

against the gold standard, both overall and split by risk level A / B.

PBR sub-perspectives in the baseline manifest (``PBR_TESTER``,
``PBR_USER``, ``PBR_DESIGNER``) are normalised to a single ``PBR``
bucket. A PBR run is a single coordinated team — perspective composition
lives inside the run, not at the bucket level.

Modes
-----
pooled
    G_<tech> = ∪_run G_<tech>_run. ``tp_<tech> = |G_<tech>|``,
    ``recall_<tech> = tp / total_gold``.
    ``tp_union = |G_UBR ∪ G_CBR ∪ G_PBR|``.
    This is the "throw everything together" view the supervisor asked for.

per_run_union_mean
    For UBR / CBR / PBR, ``tp_<tech>`` is the mean over runs of
    ``|G_<tech>_run|``; ``recall_<tech>`` is the mean of per-run recalls.
    The union column stays the pooled cross-technique union — a per-run
    cross-technique pairing is artificial (runs of different techniques
    are independent), so the headline union is reported as the pooled
    upper bound, which keeps the invariant
    ``tp_union >= max(tp_<tech>)`` intact.

Outputs
-------
- ``<outdir>/union_gold_coverage_<mode>_<scope>_n<N>_t<thr>.csv``
  — summary row
- ``<outdir>/union_gold_ids_<mode>_<scope>_n<N>_t<thr>.csv``
  — per-gold hit flags

``<scope>`` is one of ``same`` (overlap / redundancy view), ``split``
(coverage / division-of-labour view), or ``all`` (no scope_mode filter).
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

# Make the project's src/ importable so we reuse the canonical matcher.
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


ALLOWED_N = {"all", "1", "2", "3", "5", "10"}
ALLOWED_MODES = {"pooled", "per_run_union_mean"}
ALLOWED_SCOPES = {"same", "split", "all"}

# Buckets aggregated by the script. The manifest's `technique` column may
# carry one of the PBR sub-perspectives (PBR_TESTER / PBR_USER /
# PBR_DESIGNER); we normalise those down to "PBR" for the bucket name.
TECHNIQUES = ("UBR", "CBR", "PBR")


def _normalize_technique(raw: str) -> str:
    """Map a manifest technique string to a TECHNIQUES bucket name."""
    t = (raw or "").strip().upper()
    if t.startswith("PBR"):
        return "PBR"
    return t


SUMMARY_COLS = [
    "threshold", "mode", "scope", "n_filter",
    "n_runs_ubr", "n_runs_cbr", "n_runs_pbr",
    "tp_ubr", "tp_cbr", "tp_pbr", "tp_union",
    "recall_ubr", "recall_cbr", "recall_pbr", "recall_union",
    "tpA_ubr", "tpA_cbr", "tpA_pbr", "tpA_union",
    "recallA_ubr", "recallA_cbr", "recallA_pbr", "recallA_union",
    "tpB_ubr", "tpB_cbr", "tpB_pbr", "tpB_union",
    "recallB_ubr", "recallB_cbr", "recallB_pbr", "recallB_union",
    "total_gold", "total_A", "total_B",
]

DETAIL_COLS = [
    "gold_id", "risk", "position", "description",
    "hit_ubr", "hit_cbr", "hit_pbr", "hit_union",
]


# ---------------------------------------------------------------------------
# Loaders / helpers
# ---------------------------------------------------------------------------


def _load_baseline_runs(
    manifest_path: Path,
    n_filter: str,
    scope: str = "same",
) -> List[Tuple[str, str, int]]:
    """Return (run_id, technique, n_reviewers) for status==ok and the
    requested scope filter.

    ``scope`` is one of ``"same"``, ``"split"``, or ``"all"``. ``"all"``
    disables the scope_mode filter entirely.
    """
    if scope not in ALLOWED_SCOPES:
        raise ValueError(f"Unknown scope {scope!r}; expected one of {sorted(ALLOWED_SCOPES)}")
    if not manifest_path.exists():
        raise FileNotFoundError(f"Baseline manifest not found: {manifest_path}")
    n_int: Optional[int] = None if n_filter == "all" else int(n_filter)
    out: List[Tuple[str, str, int]] = []
    with manifest_path.open("r", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            if (row.get("status") or "").strip() != "ok":
                continue
            row_scope = (row.get("scope_mode") or "").strip()
            if scope != "all" and row_scope != scope:
                continue
            tech = _normalize_technique(row.get("technique") or "")
            if tech not in TECHNIQUES:
                continue
            try:
                n = int(row.get("n_reviewers") or "0")
            except ValueError:
                continue
            if n_int is not None and n != n_int:
                continue
            rid = (row.get("run_id") or "").strip()
            if rid:
                out.append((rid, tech, n))
    return out


def _load_raw_defects(path: Path) -> List[Dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


_REVIEWER_NUM_RE = re.compile(r"reviewer[_-]?(\d+)", re.IGNORECASE)


def _reviewer_index(reviewer_id: str) -> int:
    m = _REVIEWER_NUM_RE.search(reviewer_id or "")
    return int(m.group(1)) if m else 10**9


def _normalize_fault_type(value: str) -> FaultType:
    v = (value or "").strip().upper()
    if v == "M":
        return FaultType.M
    if v == "W":
        return FaultType.W
    return FaultType.UNK


def _row_to_defect(row: Dict[str, str]) -> Defect:
    description = (row.get("description_raw") or "").strip()
    position = (row.get("position") or "").strip() or "unknown"
    page_hint = (row.get("page_hint") or "").strip() or None
    return Defect(
        id=(row.get("defect_id") or "").strip() or f"raw_{id(row)}",
        position=position,
        page_hint=page_hint,
        risk=RiskLevel.UNK,
        fault_type=_normalize_fault_type(row.get("fault_type") or ""),
        description=description,
        evidence=description,
        confidence=0.8,
        reviewer_id=row.get("reviewer_id") or None,
    )


# ---------------------------------------------------------------------------
# Per-reviewer / per-run matching
# ---------------------------------------------------------------------------


def reviewer_gold_hits(
    rows: Sequence[Dict[str, str]],
    gold: Sequence[GoldDefect],
    matcher: DefectMatcher,
) -> Dict[str, Set[str]]:
    """Return {reviewer_id: set(gold_id)} for each reviewer in this run."""
    by_reviewer: Dict[str, List[Dict[str, str]]] = defaultdict(list)
    for r in rows:
        by_reviewer[(r.get("reviewer_id") or "").strip()].append(r)

    out: Dict[str, Set[str]] = {}
    for rid, r_rows in by_reviewer.items():
        if not rid:
            continue
        found = [_row_to_defect(r) for r in r_rows]
        matches, _stats = matcher.match(found, list(gold))
        hits: Set[str] = set()
        for m in matches:
            if m.match_type in (MatchType.EXACT, MatchType.PARTIAL) and m.gold_id:
                hits.add(m.gold_id)
        out[rid] = hits
    return out


def run_gold_hits(reviewer_hits: Dict[str, Set[str]]) -> Set[str]:
    """Union of all reviewers' gold hits in this run."""
    out: Set[str] = set()
    for hits in reviewer_hits.values():
        out |= hits
    return out


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------


def _safe_recall(tp: float, total: int) -> float:
    return (tp / total) if total > 0 else 0.0


def aggregate(
    per_run_hits: Dict[str, Set[str]],
    techniques_by_run: Dict[str, str],
    gold: Sequence[GoldDefect],
    mode: str,
) -> Dict[str, object]:
    """Compute summary numbers for UBR / CBR / PBR / UNION.

    Returns a dict matching SUMMARY_COLS (minus threshold/mode/n_filter,
    which are filled in by the caller).
    """
    runs_by_tech: Dict[str, List[str]] = defaultdict(list)
    for rid, tech in techniques_by_run.items():
        runs_by_tech[_normalize_technique(tech)].append(rid)

    # Pooled sets per technique bucket (always computed; needed for
    # union and detail CSV) plus the cross-technique union.
    pooled: Dict[str, Set[str]] = {t: set() for t in TECHNIQUES}
    for tech, runs in runs_by_tech.items():
        if tech not in pooled:
            continue
        for rid in runs:
            pooled[tech] |= per_run_hits.get(rid, set())
    pooled_union: Set[str] = set()
    for t in TECHNIQUES:
        pooled_union |= pooled[t]

    risk_of = {g.id: g.risk for g in gold}
    total_gold = len(gold)
    total_A = sum(1 for g in gold if g.risk == RiskLevel.A)
    total_B = sum(1 for g in gold if g.risk == RiskLevel.B)

    def _split_counts(ids: Set[str]) -> Tuple[int, int]:
        a = sum(1 for gid in ids if risk_of.get(gid) == RiskLevel.A)
        b = sum(1 for gid in ids if risk_of.get(gid) == RiskLevel.B)
        return a, b

    # Per-technique tp / tpA / tpB. The two modes share the same return
    # shape; pooled uses set sizes, per_run_union_mean uses run-averaged
    # counts.
    tp_per_tech: Dict[str, float] = {}
    tpA_per_tech: Dict[str, float] = {}
    tpB_per_tech: Dict[str, float] = {}

    if mode == "pooled":
        for t in TECHNIQUES:
            tp_per_tech[t] = float(len(pooled[t]))
            a, b = _split_counts(pooled[t])
            tpA_per_tech[t] = float(a)
            tpB_per_tech[t] = float(b)
    elif mode == "per_run_union_mean":
        def _mean_count(runs: Sequence[str]) -> Tuple[float, float, float]:
            if not runs:
                return 0.0, 0.0, 0.0
            tots, as_, bs = [], [], []
            for rid in runs:
                hits = per_run_hits.get(rid, set())
                tots.append(len(hits))
                a, b = _split_counts(hits)
                as_.append(a)
                bs.append(b)
            return (
                sum(tots) / len(tots),
                sum(as_) / len(as_),
                sum(bs) / len(bs),
            )

        for t in TECHNIQUES:
            tp_per_tech[t], tpA_per_tech[t], tpB_per_tech[t] = _mean_count(
                runs_by_tech.get(t, [])
            )
    else:
        raise ValueError(f"Unknown mode: {mode}")

    # Union row uses pooled cross-technique union — see module docstring.
    tp_union = float(len(pooled_union))
    tpA_union, tpB_union = _split_counts(pooled_union)

    result: Dict[str, object] = {
        "tp_union": tp_union,
        "recall_union": _safe_recall(tp_union, total_gold),
        "tpA_union": float(tpA_union),
        "recallA_union": _safe_recall(tpA_union, total_A),
        "tpB_union": float(tpB_union),
        "recallB_union": _safe_recall(tpB_union, total_B),
        "total_gold": total_gold,
        "total_A": total_A,
        "total_B": total_B,
        "_pooled_union": pooled_union,
    }
    for t in TECHNIQUES:
        suffix = t.lower()
        result[f"n_runs_{suffix}"] = len(runs_by_tech.get(t, []))
        result[f"tp_{suffix}"] = tp_per_tech[t]
        result[f"recall_{suffix}"] = _safe_recall(tp_per_tech[t], total_gold)
        result[f"tpA_{suffix}"] = tpA_per_tech[t]
        result[f"recallA_{suffix}"] = _safe_recall(tpA_per_tech[t], total_A)
        result[f"tpB_{suffix}"] = tpB_per_tech[t]
        result[f"recallB_{suffix}"] = _safe_recall(tpB_per_tech[t], total_B)
        result[f"_pooled_{suffix}"] = pooled[t]
    return result


# ---------------------------------------------------------------------------
# Sanity checks
# ---------------------------------------------------------------------------


def assert_sanity(summary: Dict[str, object]) -> List[str]:
    """Return a list of violation strings; empty means all checks pass."""
    violations: List[str] = []
    total_gold = int(summary["total_gold"])  # type: ignore[arg-type]
    total_A = int(summary["total_A"])  # type: ignore[arg-type]
    total_B = int(summary["total_B"])  # type: ignore[arg-type]

    EPS = 1e-9

    def _cmp(a: float, b: float) -> bool:
        return a + EPS >= b

    for t in TECHNIQUES:
        suffix = t.lower()
        if not _cmp(float(summary["tp_union"]), float(summary[f"tp_{suffix}"])):
            violations.append(f"tp_union < tp_{suffix}")
        if not _cmp(
            float(summary["recall_union"]), float(summary[f"recall_{suffix}"])
        ):
            violations.append(f"recall_union < recall_{suffix}")

    tp_cols = [f"tp_{t.lower()}" for t in TECHNIQUES] + ["tp_union"]
    for col in tp_cols:
        if float(summary[col]) > total_gold + EPS:
            violations.append(f"{col} > total_gold ({total_gold})")
    risk_cols = []
    for prefix, total in (("tpA_", total_A), ("tpB_", total_B)):
        for t in TECHNIQUES:
            risk_cols.append((f"{prefix}{t.lower()}", total))
        risk_cols.append((f"{prefix}union", total))
    for col, total in risk_cols:
        if float(summary[col]) > total + EPS:
            violations.append(f"{col} > total ({total})")
    return violations


# ---------------------------------------------------------------------------
# Writers
# ---------------------------------------------------------------------------


def _gold_sort_key(g: GoldDefect) -> Tuple[int, str]:
    try:
        return (0, f"{int(g.id):08d}")
    except (TypeError, ValueError):
        return (1, str(g.id))


def _fmt(x: float, digits: int = 4) -> str:
    return f"{x:.{digits}f}"


def write_summary_csv(out_path: Path, summary: Dict[str, object], threshold: float,
                      mode: str, n_filter: str, scope: str) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    row: Dict[str, object] = {
        "threshold": f"{threshold:.2f}",
        "mode": mode,
        "scope": scope,
        "n_filter": n_filter,
        "tp_union": _fmt(float(summary["tp_union"]), 2),
        "recall_union": _fmt(float(summary["recall_union"])),
        "tpA_union": _fmt(float(summary["tpA_union"]), 2),
        "recallA_union": _fmt(float(summary["recallA_union"])),
        "tpB_union": _fmt(float(summary["tpB_union"]), 2),
        "recallB_union": _fmt(float(summary["recallB_union"])),
        "total_gold": summary["total_gold"],
        "total_A": summary["total_A"],
        "total_B": summary["total_B"],
    }
    for t in TECHNIQUES:
        suffix = t.lower()
        row[f"n_runs_{suffix}"] = summary[f"n_runs_{suffix}"]
        row[f"tp_{suffix}"] = _fmt(float(summary[f"tp_{suffix}"]), 2)
        row[f"recall_{suffix}"] = _fmt(float(summary[f"recall_{suffix}"]))
        row[f"tpA_{suffix}"] = _fmt(float(summary[f"tpA_{suffix}"]), 2)
        row[f"recallA_{suffix}"] = _fmt(float(summary[f"recallA_{suffix}"]))
        row[f"tpB_{suffix}"] = _fmt(float(summary[f"tpB_{suffix}"]), 2)
        row[f"recallB_{suffix}"] = _fmt(float(summary[f"recallB_{suffix}"]))
    with out_path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=SUMMARY_COLS)
        w.writeheader()
        w.writerow({c: row.get(c, "") for c in SUMMARY_COLS})


def write_detail_csv(out_path: Path, gold: Sequence[GoldDefect],
                     summary: Dict[str, object]) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    pooled_union: Set[str] = summary["_pooled_union"]  # type: ignore[assignment]
    pooled_by_tech: Dict[str, Set[str]] = {
        t: summary[f"_pooled_{t.lower()}"]  # type: ignore[assignment]
        for t in TECHNIQUES
    }

    with out_path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=DETAIL_COLS)
        w.writeheader()
        for g in sorted(gold, key=_gold_sort_key):
            row = {
                "gold_id": g.id,
                "risk": g.risk.value,
                "position": g.position,
                "description": g.description,
                "hit_union": 1 if g.id in pooled_union else 0,
            }
            for t in TECHNIQUES:
                row[f"hit_{t.lower()}"] = 1 if g.id in pooled_by_tech[t] else 0
            w.writerow(row)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--from-baseline", required=True, help="Path to baseline manifest CSV")
    p.add_argument("--gold", required=True, help="Path to gold standard XLS")
    p.add_argument("--threshold", type=float, default=0.65,
                   help="Description-similarity threshold (default: 0.65)")
    p.add_argument("--outdir", default="results/union_coverage",
                   help="Output directory (default: results/union_coverage)")
    p.add_argument("--n-reviewers", default="all", choices=sorted(ALLOWED_N),
                   help="Reviewer-group filter (default: all)")
    p.add_argument("--mode", default="pooled", choices=sorted(ALLOWED_MODES),
                   help="Aggregation mode (default: pooled)")
    p.add_argument("--scope", default="same", choices=sorted(ALLOWED_SCOPES),
                   help=(
                       "scope_mode filter in baseline manifest "
                       "(same = overlap/redundancy, split = "
                       "coverage/division-of-labour, all = no filter). "
                       "Default: same."
                   ))
    p.add_argument("--results-dir", default="results",
                   help="Directory holding raw_defects_*.csv (default: results)")
    p.add_argument("--strict", action="store_true",
                   help="Exit non-zero if any sanity invariant is violated.")
    return p


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_arg_parser().parse_args(argv)
    results_dir = Path(args.results_dir)
    outdir = Path(args.outdir)

    runs = _load_baseline_runs(
        Path(args.from_baseline),
        n_filter=args.n_reviewers,
        scope=args.scope,
    )
    if not runs:
        print("[union_cov] No matching runs.", file=sys.stderr)
        return 1
    print(f"[union_cov] Selected {len(runs)} run(s) "
          f"(n={args.n_reviewers}, scope={args.scope}).")

    print(f"[union_cov] Loading gold from {args.gold} ...")
    gold = GoldLoader(args.gold).load()
    print(f"[union_cov]   gold defects: total={len(gold)}, "
          f"A={sum(1 for g in gold if g.risk == RiskLevel.A)}, "
          f"B={sum(1 for g in gold if g.risk == RiskLevel.B)}")

    matcher = DefectMatcher(description_threshold=args.threshold)
    per_run_hits: Dict[str, Set[str]] = {}
    techniques_by_run: Dict[str, str] = {}
    skipped: List[str] = []
    for run_id, tech, _n in runs:
        raw_path = results_dir / f"raw_defects_{run_id}.csv"
        rows = _load_raw_defects(raw_path)
        if not rows:
            skipped.append(f"{run_id} (no raw defects at {raw_path})")
            continue
        rev_hits = reviewer_gold_hits(rows, gold, matcher)
        per_run_hits[run_id] = run_gold_hits(rev_hits)
        techniques_by_run[run_id] = tech

    if skipped:
        print(f"[union_cov] Skipped {len(skipped)} run(s):", file=sys.stderr)
        for s in skipped:
            print(f"  - {s}", file=sys.stderr)
    if not techniques_by_run:
        print("[union_cov] No runs produced matches.", file=sys.stderr)
        return 1

    summary = aggregate(per_run_hits, techniques_by_run, gold, mode=args.mode)

    violations = assert_sanity(summary)
    if violations:
        print("[union_cov] SANITY VIOLATIONS:", file=sys.stderr)
        for v in violations:
            print(f"  - {v}", file=sys.stderr)
        if args.strict:
            return 2
    else:
        print("[union_cov] Sanity checks PASSED.")

    thr_tag = f"{args.threshold:.2f}".replace(".", "")
    summary_out = (
        outdir
        / f"union_gold_coverage_{args.mode}_{args.scope}_n{args.n_reviewers}_t{thr_tag}.csv"
    )
    detail_out = (
        outdir
        / f"union_gold_ids_{args.mode}_{args.scope}_n{args.n_reviewers}_t{thr_tag}.csv"
    )

    write_summary_csv(
        summary_out, summary, args.threshold, args.mode, args.n_reviewers, args.scope
    )
    write_detail_csv(detail_out, gold, summary)

    print(f"[union_cov] Wrote {summary_out}")
    print(f"[union_cov] Wrote {detail_out}")
    print(
        f"[union_cov] tp_ubr={float(summary['tp_ubr']):.2f}, "
        f"tp_cbr={float(summary['tp_cbr']):.2f}, "
        f"tp_pbr={float(summary['tp_pbr']):.2f}, "
        f"tp_union={float(summary['tp_union']):.2f} / {summary['total_gold']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
