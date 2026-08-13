#!/usr/bin/env python3
"""Share-of-reviewers-per-fault plots (UBR vs CBR).

Reproduces the paper figures
  * "Share of reviewers that found each A-fault"
  * "Share of reviewers that found each B-fault"

Definition
----------
For a gold fault d and a group G of reviewers:

    share(d) = |{r in G : r matched d}| / |G|

A reviewer "matches" a gold fault if any of their raw defects matches it
under the canonical ``DefectMatcher`` (same matcher and threshold as
``fagan eval``). Each reviewer counts at most once per gold fault.

Modes
-----
  pooled        — pool all reviewers over all selected runs; the denominator
                  is n_runs * n_reviewers.
  per_run_mean  — compute share(d) per run, then average over runs.

Outputs (per risk level X in {A, B})
------------------------------------
  <outdir>/fault_share_<X>_<scope>_n<N>_<mode>_t<thr>.csv          (wide)
  <outdir>/fault_share_long_<X>_<scope>_n<N>_<mode>_t<thr>.csv     (long)
  <outdir>/fault_share_<X>_<scope>_n<N>_<mode>_t<thr>.png          (grouped bar plot)

``<scope>`` is one of ``same`` (overlap / redundancy view), ``split``
(coverage / division-of-labour view), or ``all`` (no scope_mode filter).

The gold standard is only read by the evaluation module. No new inspection
runs are started; gold files are not modified.
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

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


ALLOWED_N = {1, 2, 3, 5, 10}
ALLOWED_MODES = {"pooled", "per_run_mean"}
ALLOWED_SCOPES = {"same", "split", "all"}

WIDE_COLS_TEMPLATE = [
    "gold_id", "gold_position", "gold_risk", "gold_description",
    # the four per-technique columns are appended at write time
]
LONG_COLS = ["gold_id", "gold_risk", "technique", "share", "count", "denom"]


# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------


def _load_baseline_runs(
    manifest_path: Path,
    techniques: Sequence[str],
    n_reviewers: int,
    scope: str = "same",
    config_contains: Optional[str] = None,
) -> List[Tuple[str, str]]:
    """Return [(run_id, technique)] filtered by status/technique/n/scope.

    ``scope`` is one of ``"same"``, ``"split"``, or ``"all"``. ``"all"``
    disables the scope_mode filter entirely. ``config_contains`` is an
    optional case-sensitive substring that must appear in the row's
    ``config_path`` (useful for picking out e.g. ``split_soft_n10`` runs).
    """
    if scope not in ALLOWED_SCOPES:
        raise ValueError(
            f"Unknown scope {scope!r}; expected one of {sorted(ALLOWED_SCOPES)}"
        )
    if not manifest_path.exists():
        raise FileNotFoundError(f"Baseline manifest not found: {manifest_path}")
    techs_upper = {t.upper() for t in techniques}
    out: List[Tuple[str, str]] = []
    with manifest_path.open("r", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            if (row.get("status") or "").strip() != "ok":
                continue
            tech = (row.get("technique") or "").strip().upper()
            if tech not in techs_upper:
                continue
            row_scope = (row.get("scope_mode") or "").strip()
            if scope != "all" and row_scope != scope:
                continue
            if config_contains and config_contains not in (row.get("config_path") or ""):
                continue
            try:
                n = int(row.get("n_reviewers") or "0")
            except ValueError:
                continue
            if n != n_reviewers:
                continue
            rid = (row.get("run_id") or "").strip()
            if rid:
                out.append((rid, tech))
    return out


_REVIEWER_NUM_RE = re.compile(r"reviewer[_-]?(\d+)", re.IGNORECASE)


def _reviewer_index(reviewer_id: str) -> int:
    m = _REVIEWER_NUM_RE.search(reviewer_id or "")
    return int(m.group(1)) if m else 10**9


def _load_raw_defects(path: Path) -> List[Dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


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
        evidence=description,  # raw CSV has no separate evidence field
        confidence=0.8,
        reviewer_id=row.get("reviewer_id") or None,
    )


# ---------------------------------------------------------------------------
# Per-reviewer matching
# ---------------------------------------------------------------------------


def reviewer_gold_hits(
    rows: Sequence[Dict[str, str]],
    gold: Sequence[GoldDefect],
    matcher: DefectMatcher,
) -> Dict[str, Set[str]]:
    """Return {reviewer_id: set(gold_id)} of gold defects each reviewer matched.

    A reviewer hits a gold id if any of their raw defects ends up classified
    as EXACT or PARTIAL by ``DefectMatcher``. Each reviewer is matched
    independently — we do NOT do a global one-to-one assignment, because
    the question here is "did this reviewer find d", not "who is the unique
    owner of d".
    """
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


# ---------------------------------------------------------------------------
# Aggregation (pooled / per_run_mean)
# ---------------------------------------------------------------------------


def aggregate_shares(
    per_run_hits: Dict[str, Dict[str, Set[str]]],
    techniques_by_run: Dict[str, str],
    n_reviewers: int,
    gold_ids: Sequence[str],
    mode: str,
) -> Dict[str, Dict[str, Tuple[float, int, int]]]:
    """Aggregate shares per technique.

    Returns a nested dict:
        {technique: {gold_id: (share, count, denom)}}

    pooled
        count  = sum over runs of |reviewers in run that matched d|
        denom  = sum over runs of (reviewers actually present in raw_defects
                 for that run, capped at n_reviewers)
        share  = count / denom

    per_run_mean
        per_run_share(d) = (# reviewers in run that matched d) / (# reviewers in run)
        share = mean(per_run_share over runs)
        count = sum of per-run numerators (informational)
        denom = sum of per-run denominators (informational)
    """
    by_tech: Dict[str, Dict[str, Tuple[float, int, int]]] = {}
    # Group run_ids by technique
    runs_by_tech: Dict[str, List[str]] = defaultdict(list)
    for rid, tech in techniques_by_run.items():
        runs_by_tech[tech].append(rid)

    for tech, run_ids in runs_by_tech.items():
        if mode == "pooled":
            count: Dict[str, int] = defaultdict(int)
            denom = 0
            for rid in run_ids:
                hits_by_rev = per_run_hits.get(rid, {})
                # cap denominator at n_reviewers in case raw CSV has more
                rev_ids = sorted(hits_by_rev.keys(), key=_reviewer_index)
                rev_ids = rev_ids[:n_reviewers]
                denom += len(rev_ids)
                for r in rev_ids:
                    for gid in hits_by_rev[r]:
                        count[gid] += 1
            per_gold: Dict[str, Tuple[float, int, int]] = {}
            for gid in gold_ids:
                c = count.get(gid, 0)
                share = (c / denom) if denom > 0 else 0.0
                per_gold[gid] = (share, c, denom)
            by_tech[tech] = per_gold

        elif mode == "per_run_mean":
            per_gold_shares: Dict[str, List[float]] = defaultdict(list)
            count_sum: Dict[str, int] = defaultdict(int)
            denom_sum = 0
            for rid in run_ids:
                hits_by_rev = per_run_hits.get(rid, {})
                rev_ids = sorted(hits_by_rev.keys(), key=_reviewer_index)
                rev_ids = rev_ids[:n_reviewers]
                n_in_run = len(rev_ids)
                denom_sum += n_in_run
                if n_in_run == 0:
                    for gid in gold_ids:
                        per_gold_shares[gid].append(0.0)
                    continue
                for gid in gold_ids:
                    c_run = sum(1 for r in rev_ids if gid in hits_by_rev[r])
                    per_gold_shares[gid].append(c_run / n_in_run)
                    count_sum[gid] += c_run
            per_gold = {}
            for gid in gold_ids:
                shares = per_gold_shares[gid]
                mean_share = sum(shares) / len(shares) if shares else 0.0
                per_gold[gid] = (mean_share, count_sum.get(gid, 0), denom_sum)
            by_tech[tech] = per_gold

        else:
            raise ValueError(f"Unknown mode: {mode}")
    return by_tech


# ---------------------------------------------------------------------------
# Writers
# ---------------------------------------------------------------------------


def _gold_sort_key(gd: GoldDefect) -> Tuple[int, str]:
    """Stable sort key — numeric ID first, then string."""
    try:
        return (0, f"{int(gd.id):08d}")
    except (TypeError, ValueError):
        return (1, str(gd.id))


def write_wide_csv(
    out_path: Path,
    gold_subset: Sequence[GoldDefect],
    techniques: Sequence[str],
    shares_by_tech: Dict[str, Dict[str, Tuple[float, int, int]]],
) -> None:
    cols = list(WIDE_COLS_TEMPLATE)
    for t in techniques:
        cols.append(f"share_{t}")
    for t in techniques:
        cols.append(f"count_{t}")
        cols.append(f"denom_{t}")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for gd in gold_subset:
            row: Dict[str, object] = {
                "gold_id": gd.id,
                "gold_position": gd.position,
                "gold_risk": gd.risk.value,
                "gold_description": gd.description,
            }
            for t in techniques:
                share, _c, _d = shares_by_tech.get(t, {}).get(gd.id, (0.0, 0, 0))
                row[f"share_{t}"] = f"{share:.4f}"
            for t in techniques:
                _share, c, d = shares_by_tech.get(t, {}).get(gd.id, (0.0, 0, 0))
                row[f"count_{t}"] = c
                row[f"denom_{t}"] = d
            w.writerow(row)


def write_long_csv(
    out_path: Path,
    gold_subset: Sequence[GoldDefect],
    techniques: Sequence[str],
    shares_by_tech: Dict[str, Dict[str, Tuple[float, int, int]]],
) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=LONG_COLS)
        w.writeheader()
        for gd in gold_subset:
            for t in techniques:
                share, c, d = shares_by_tech.get(t, {}).get(gd.id, (0.0, 0, 0))
                w.writerow({
                    "gold_id": gd.id,
                    "gold_risk": gd.risk.value,
                    "technique": t,
                    "share": f"{share:.4f}",
                    "count": c,
                    "denom": d,
                })


# ---------------------------------------------------------------------------
# Plot
# ---------------------------------------------------------------------------


def make_plot(
    out_path: Path,
    risk_letter: str,
    gold_subset: Sequence[GoldDefect],
    techniques: Sequence[str],
    shares_by_tech: Dict[str, Dict[str, Tuple[float, int, int]]],
    n_reviewers: int,
    threshold: float,
    mode: str,
) -> None:
    # Defer matplotlib import so --help works without it installed.
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    labels = [str(gd.id) for gd in gold_subset]
    x = list(range(len(labels)))
    n_t = len(techniques)
    total_width = 0.8
    bar_width = total_width / max(n_t, 1)

    fig, ax = plt.subplots(figsize=(max(8.0, 0.55 * len(labels) + 2.0), 4.5))
    for i, t in enumerate(techniques):
        ys = [shares_by_tech.get(t, {}).get(gd.id, (0.0, 0, 0))[0] for gd in gold_subset]
        offsets = [xi - total_width / 2 + bar_width / 2 + i * bar_width for xi in x]
        ax.bar(offsets, ys, width=bar_width, label=t)

    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=60, ha="right")
    ax.set_ylim(0.0, 1.0)
    ax.set_ylabel("Share of reviewers")
    ax.set_xlabel(f"Gold fault id (Risk {risk_letter})")
    ax.set_title(
        f"Share of reviewers that found each {risk_letter}-fault "
        f"(n={n_reviewers}, threshold={threshold:.2f}, {mode})"
    )
    ax.legend(loc="upper right")
    ax.grid(axis="y", linestyle=":", alpha=0.5)
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--from-baseline", required=True, help="Path to baseline manifest CSV")
    p.add_argument("--gold", required=True, help="Path to gold standard XLS")
    p.add_argument("--threshold", type=float, default=0.65,
                   help="Description-similarity threshold (default: 0.65)")
    p.add_argument("--n-reviewers", type=int, default=10,
                   help="Reviewer group size (allowed: 1,2,3,5,10; default: 10)")
    p.add_argument("--outdir", default="results/fault_share",
                   help="Output directory (default: results/fault_share)")
    p.add_argument("--techniques", nargs="+", default=["UBR", "CBR"],
                   help="Techniques to compare (default: UBR CBR)")
    p.add_argument("--mode", choices=sorted(ALLOWED_MODES), default="pooled",
                   help="Aggregation mode (default: pooled)")
    p.add_argument("--scope", default="same", choices=sorted(ALLOWED_SCOPES),
                   help=(
                       "scope_mode filter in baseline manifest "
                       "(same = overlap/redundancy, split = "
                       "coverage/division-of-labour, all = no filter). "
                       "Default: same."
                   ))
    p.add_argument("--config-contains", default=None,
                   help=(
                       "Optional case-sensitive substring that must appear in "
                       "the manifest's config_path column (e.g. 'split_soft_n10' "
                       "to keep only that experiment family)."
                   ))
    p.add_argument("--results-dir", default="results",
                   help="Directory holding raw_defects_*.csv (default: results)")
    return p


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_arg_parser().parse_args(argv)

    if args.n_reviewers not in ALLOWED_N:
        print(
            f"[fault_share] ERROR: --n-reviewers must be one of {sorted(ALLOWED_N)}.",
            file=sys.stderr,
        )
        return 2

    techniques = [t.upper() for t in args.techniques]
    outdir = Path(args.outdir)
    results_dir = Path(args.results_dir)

    # 1. Resolve runs
    runs = _load_baseline_runs(
        Path(args.from_baseline),
        techniques=techniques,
        n_reviewers=args.n_reviewers,
        scope=args.scope,
        config_contains=args.config_contains,
    )
    if not runs:
        print("[fault_share] No matching runs in baseline manifest.", file=sys.stderr)
        return 1
    cc_note = (
        f", config_contains={args.config_contains!r}" if args.config_contains else ""
    )
    print(f"[fault_share] Selected {len(runs)} run(s) "
          f"(techniques={techniques}, n={args.n_reviewers}, scope={args.scope}{cc_note}).")

    # 2. Load gold and split by risk
    print(f"[fault_share] Loading gold from {args.gold} ...")
    gold = GoldLoader(args.gold).load()
    gold_sorted = sorted(gold, key=_gold_sort_key)
    gold_A = [g for g in gold_sorted if g.risk == RiskLevel.A]
    gold_B = [g for g in gold_sorted if g.risk == RiskLevel.B]
    all_gold_ids = [g.id for g in gold_sorted]
    print(f"[fault_share]   gold: total={len(gold)}, A={len(gold_A)}, B={len(gold_B)}")

    # 3. Per-reviewer matching for each run (cache results in per_run_hits)
    matcher = DefectMatcher(description_threshold=args.threshold)
    per_run_hits: Dict[str, Dict[str, Set[str]]] = {}
    techniques_by_run: Dict[str, str] = {}
    skipped: List[str] = []
    for run_id, tech in runs:
        raw_path = results_dir / f"raw_defects_{run_id}.csv"
        rows = _load_raw_defects(raw_path)
        if not rows:
            skipped.append(f"{run_id} (no raw defects at {raw_path})")
            continue
        per_run_hits[run_id] = reviewer_gold_hits(rows, gold, matcher)
        techniques_by_run[run_id] = tech

    if skipped:
        print(f"[fault_share] Skipped {len(skipped)} run(s):", file=sys.stderr)
        for s in skipped:
            print(f"  - {s}", file=sys.stderr)
    if not techniques_by_run:
        print("[fault_share] No runs produced reviewer matches.", file=sys.stderr)
        return 1

    # 4. Aggregate
    shares_by_tech = aggregate_shares(
        per_run_hits=per_run_hits,
        techniques_by_run=techniques_by_run,
        n_reviewers=args.n_reviewers,
        gold_ids=all_gold_ids,
        mode=args.mode,
    )

    # Ensure every requested technique has an entry, even if no runs.
    for t in techniques:
        shares_by_tech.setdefault(t, {})

    # 5. Write outputs (A and B)
    thr_tag = f"{args.threshold:.2f}".replace(".", "")
    n_tag = args.n_reviewers
    mode_tag = args.mode
    scope_tag = args.scope

    for letter, subset in (("A", gold_A), ("B", gold_B)):
        wide = (
            outdir
            / f"fault_share_{letter}_{scope_tag}_n{n_tag}_{mode_tag}_t{thr_tag}.csv"
        )
        long_csv = (
            outdir
            / f"fault_share_long_{letter}_{scope_tag}_n{n_tag}_{mode_tag}_t{thr_tag}.csv"
        )
        png = (
            outdir
            / f"fault_share_{letter}_{scope_tag}_n{n_tag}_{mode_tag}_t{thr_tag}.png"
        )

        write_wide_csv(wide, subset, techniques, shares_by_tech)
        write_long_csv(long_csv, subset, techniques, shares_by_tech)
        make_plot(
            png, letter, subset, techniques, shares_by_tech,
            n_reviewers=args.n_reviewers, threshold=args.threshold, mode=args.mode,
        )
        print(f"[fault_share] Wrote {wide}")
        print(f"[fault_share] Wrote {long_csv}")
        print(f"[fault_share] Wrote {png}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
