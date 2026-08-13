"""Unit tests for the ``--scope`` filter in ``scripts/union_gold_coverage``.

The script is a thin CLI around small helpers; the scope filter lives in
``_load_baseline_runs``. We feed it a dummy manifest with a mix of
``same`` and ``split`` rows (plus a not-OK status, which must always be
dropped) and assert that:

* ``scope="same"`` keeps only same-scope rows;
* ``scope="split"`` keeps only split-scope rows;
* ``scope="all"`` keeps every status-OK row;
* an unknown scope raises ``ValueError`` (defensive guard).
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "union_gold_coverage.py"


def _load_module():
    """Load union_gold_coverage as a module without running the CLI."""
    spec = importlib.util.spec_from_file_location("union_gold_coverage", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules["union_gold_coverage"] = module
    assert spec.loader is not None  # for type checkers
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def ugc():
    return _load_module()


@pytest.fixture
def dummy_manifest(tmp_path: Path) -> Path:
    """Manifest with same/split/ok/failed rows mixed."""
    header = (
        "timestamp,run_id,technique,n_reviewers,scope_mode,"
        "config_path,run_path,metrics_path,status\n"
    )
    rows = [
        # 3 OK same-scope rows (1 UBR n=1, 1 UBR n=10, 1 CBR n=3)
        "2026-01-01T00:00:00,sweep_ubr_same_n1_aaa,UBR,1,same,c,r,m,ok\n",
        "2026-01-01T00:00:01,sweep_ubr_same_n10_bbb,UBR,10,same,c,r,m,ok\n",
        "2026-01-01T00:00:02,sweep_cbr_same_n3_ccc,CBR,3,same,c,r,m,ok\n",
        # 2 OK split-scope rows
        "2026-01-01T00:00:03,sweep_ubr_split_n3_ddd,UBR,3,split,c,r,m,ok\n",
        "2026-01-01T00:00:04,sweep_cbr_split_n3_eee,CBR,3,split,c,r,m,ok\n",
        # 1 failed row (must always be dropped, regardless of scope)
        "2026-01-01T00:00:05,sweep_ubr_same_n5_zzz,UBR,5,same,c,r,m,failed\n",
        # 1 PBR row — accepted now: the union script normalises PBR_*
        # sub-perspectives to a single "PBR" bucket.
        "2026-01-01T00:00:06,sweep_pbr_split_n1_qqq,PBR_USER,1,split,c,r,m,ok\n",
        # 1 row with an unknown technique — still dropped.
        "2026-01-01T00:00:07,sweep_xyz_n1_xxx,XYZ,1,same,c,r,m,ok\n",
    ]
    path = tmp_path / "baseline.csv"
    path.write_text(header + "".join(rows), encoding="utf-8")
    return path


class TestScopeFilter:
    def test_same_keeps_only_same_scope(self, ugc, dummy_manifest):
        runs = ugc._load_baseline_runs(dummy_manifest, n_filter="all", scope="same")
        ids = {rid for rid, _t, _n in runs}
        assert ids == {
            "sweep_ubr_same_n1_aaa",
            "sweep_ubr_same_n10_bbb",
            "sweep_cbr_same_n3_ccc",
        }

    def test_split_keeps_split_scope_including_pbr(self, ugc, dummy_manifest):
        runs = ugc._load_baseline_runs(dummy_manifest, n_filter="all", scope="split")
        ids = {rid for rid, _t, _n in runs}
        # PBR_USER row passes the technique filter now (normalised to PBR).
        assert ids == {
            "sweep_ubr_split_n3_ddd",
            "sweep_cbr_split_n3_eee",
            "sweep_pbr_split_n1_qqq",
        }
        # And it is reported under the canonical "PBR" bucket name.
        techs = {rid: t for rid, t, _n in runs}
        assert techs["sweep_pbr_split_n1_qqq"] == "PBR"

    def test_all_keeps_every_ok_ubr_cbr_pbr_row(self, ugc, dummy_manifest):
        runs = ugc._load_baseline_runs(dummy_manifest, n_filter="all", scope="all")
        ids = {rid for rid, _t, _n in runs}
        # 3 same + 2 split + 1 PBR = 6; failed row and unknown-technique
        # row dropped.
        assert ids == {
            "sweep_ubr_same_n1_aaa",
            "sweep_ubr_same_n10_bbb",
            "sweep_cbr_same_n3_ccc",
            "sweep_ubr_split_n3_ddd",
            "sweep_cbr_split_n3_eee",
            "sweep_pbr_split_n1_qqq",
        }

    def test_n_filter_still_applied_per_scope(self, ugc, dummy_manifest):
        runs = ugc._load_baseline_runs(dummy_manifest, n_filter="3", scope="all")
        ids = {rid for rid, _t, _n in runs}
        assert ids == {
            "sweep_cbr_same_n3_ccc",
            "sweep_ubr_split_n3_ddd",
            "sweep_cbr_split_n3_eee",
        }

    def test_unknown_technique_dropped(self, ugc, dummy_manifest):
        runs = ugc._load_baseline_runs(dummy_manifest, n_filter="all", scope="all")
        ids = {rid for rid, _t, _n in runs}
        assert "sweep_xyz_n1_xxx" not in ids

    def test_unknown_scope_raises(self, ugc, dummy_manifest):
        with pytest.raises(ValueError):
            ugc._load_baseline_runs(dummy_manifest, n_filter="all", scope="nope")


class TestScopeChoicesInCLI:
    def test_argparser_exposes_scope_choices(self, ugc):
        parser = ugc.build_arg_parser()
        # Find the --scope action
        action = next(a for a in parser._actions if "--scope" in a.option_strings)
        assert set(action.choices) == {"same", "split", "all"}
        assert action.default == "same"


class TestThreeTechniqueAggregation:
    """End-to-end aggregation for UBR / CBR / PBR with a synthetic gold
    set so we can assert the union semantics and the sanity invariants
    directly, without an LLM in the loop."""

    def _make_gold(self, ugc):
        # Build a tiny synthetic gold standard from RiskLevel so we can
        # control which IDs land in which risk bucket. RiskLevel is
        # imported via the same module so we do not depend on the
        # evaluation package here.
        from fagan_tool.core.schemas import FaultType, GoldDefect, RiskLevel
        return [
            GoldDefect(id="1", position="3.1", risk=RiskLevel.A,
                       fault_type=FaultType.M, description="A1"),
            GoldDefect(id="2", position="3.2", risk=RiskLevel.A,
                       fault_type=FaultType.M, description="A2"),
            GoldDefect(id="3", position="3.3", risk=RiskLevel.B,
                       fault_type=FaultType.M, description="B1"),
            GoldDefect(id="4", position="3.4", risk=RiskLevel.B,
                       fault_type=FaultType.M, description="B2"),
            GoldDefect(id="5", position="4.1", risk=RiskLevel.C,
                       fault_type=FaultType.M, description="C1"),
        ]

    def test_pooled_union_covers_all_three_techniques(self, ugc):
        gold = self._make_gold(ugc)
        per_run_hits = {
            "ubr_run_1": {"1", "2"},          # UBR finds A1, A2
            "cbr_run_1": {"3", "4"},          # CBR finds B1, B2
            "pbr_run_1": {"4", "5"},          # PBR finds B2 (overlap), C1
        }
        techniques_by_run = {
            "ubr_run_1": "UBR",
            "cbr_run_1": "CBR",
            "pbr_run_1": "PBR",
        }
        summary = ugc.aggregate(
            per_run_hits, techniques_by_run, gold, mode="pooled"
        )
        assert summary["tp_ubr"] == 2.0
        assert summary["tp_cbr"] == 2.0
        assert summary["tp_pbr"] == 2.0
        # Union over the three sets: {1,2,3,4,5} = 5
        assert summary["tp_union"] == 5.0
        # Risk breakdown
        assert summary["tpA_ubr"] == 2.0  # IDs 1, 2 are risk A
        assert summary["tpB_cbr"] == 2.0  # IDs 3, 4 are risk B
        assert summary["tpB_pbr"] == 1.0  # ID 4 only (5 is C)
        assert summary["tpA_union"] == 2.0
        assert summary["tpB_union"] == 2.0
        # n_runs counters
        assert summary["n_runs_ubr"] == 1
        assert summary["n_runs_cbr"] == 1
        assert summary["n_runs_pbr"] == 1
        # Sanity must pass.
        assert ugc.assert_sanity(summary) == []

    def test_pbr_subperspective_normalised_into_pbr_bucket(self, ugc):
        gold = self._make_gold(ugc)
        per_run_hits = {"pbr_tester_run": {"3"}}
        techniques_by_run = {"pbr_tester_run": "PBR_TESTER"}
        summary = ugc.aggregate(
            per_run_hits, techniques_by_run, gold, mode="pooled"
        )
        assert summary["tp_pbr"] == 1.0
        assert summary["tp_ubr"] == 0.0
        assert summary["tp_cbr"] == 0.0
        # PBR contributes the only union hit.
        assert summary["tp_union"] == 1.0

    def test_sanity_catches_inconsistent_union(self, ugc):
        gold = self._make_gold(ugc)
        per_run_hits = {"ubr_run_1": {"1", "2", "3"}}
        techniques_by_run = {"ubr_run_1": "UBR"}
        summary = ugc.aggregate(
            per_run_hits, techniques_by_run, gold, mode="pooled"
        )
        # Tamper with the summary to violate tp_union >= tp_ubr.
        summary["tp_union"] = 0.0
        summary["recall_union"] = 0.0
        violations = ugc.assert_sanity(summary)
        assert any("tp_union < tp_ubr" in v for v in violations)
