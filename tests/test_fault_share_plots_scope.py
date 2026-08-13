"""Unit tests for the ``--scope`` and ``--config-contains`` filters in
``scripts/fault_share_plots``.

The filter logic lives in ``_load_baseline_runs``. We feed it a dummy
manifest with a mix of ``same`` and ``split`` rows (plus a not-OK status
row, a wrong-technique row, and a wrong-N row that must always be
dropped) and assert that:

* ``scope="same"`` keeps only same-scope rows;
* ``scope="split"`` keeps only split-scope rows;
* ``scope="all"`` keeps every row that survives the other filters;
* ``config_contains`` filters the surviving rows by ``config_path``;
* an unknown scope raises ``ValueError``.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "fault_share_plots.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("fault_share_plots", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules["fault_share_plots"] = module
    assert spec.loader is not None  # for type checkers
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def fsp():
    return _load_module()


@pytest.fixture
def dummy_manifest(tmp_path: Path) -> Path:
    header = (
        "timestamp,run_id,technique,n_reviewers,scope_mode,"
        "config_path,run_path,metrics_path,status\n"
    )
    rows = [
        # 3 OK same-scope UBR/CBR rows at n=10
        "2026-01-01T00:00:00,sweep_ubr_same_n10_aaa,UBR,10,same,configs/experiments/ubr_same_n10.yaml,r,m,ok\n",
        "2026-01-01T00:00:01,sweep_cbr_same_n10_bbb,CBR,10,same,configs/experiments/cbr_same_n10.yaml,r,m,ok\n",
        "2026-01-01T00:00:02,sweep_ubr_same_n10_ccc,UBR,10,same,configs/experiments/ubr_same_n10.yaml,r,m,ok\n",
        # 2 OK split-scope rows at n=10
        "2026-01-01T00:00:03,sweep_ubr_split_soft_n10_ddd,UBR,10,split,configs/experiments/ubr_split_soft_n10.yaml,r,m,ok\n",
        "2026-01-01T00:00:04,sweep_cbr_split_soft_n10_eee,CBR,10,split,configs/experiments/cbr_split_soft_n10.yaml,r,m,ok\n",
        # 1 OK split-scope row at n=3 — must be dropped by the n filter
        "2026-01-01T00:00:05,sweep_ubr_split_n3_fff,UBR,3,split,configs/experiments/ubr_split_n3.yaml,r,m,ok\n",
        # 1 failed row — must be dropped regardless of scope
        "2026-01-01T00:00:06,sweep_ubr_same_n10_zzz,UBR,10,same,configs/experiments/ubr_same_n10.yaml,r,m,failed\n",
        # 1 row with a non-UBR/CBR technique — must be dropped
        "2026-01-01T00:00:07,sweep_pbr_split_n10_qqq,PBR_USER,10,split,configs/experiments/pbr.yaml,r,m,ok\n",
    ]
    path = tmp_path / "baseline.csv"
    path.write_text(header + "".join(rows), encoding="utf-8")
    return path


class TestScopeFilter:
    def test_same_keeps_only_same_scope(self, fsp, dummy_manifest):
        runs = fsp._load_baseline_runs(
            dummy_manifest, techniques=["UBR", "CBR"], n_reviewers=10, scope="same"
        )
        ids = {rid for rid, _t in runs}
        assert ids == {
            "sweep_ubr_same_n10_aaa",
            "sweep_cbr_same_n10_bbb",
            "sweep_ubr_same_n10_ccc",
        }

    def test_split_keeps_only_split_scope(self, fsp, dummy_manifest):
        runs = fsp._load_baseline_runs(
            dummy_manifest, techniques=["UBR", "CBR"], n_reviewers=10, scope="split"
        )
        ids = {rid for rid, _t in runs}
        # n=3 split row dropped by N filter, PBR row dropped by technique filter.
        assert ids == {
            "sweep_ubr_split_soft_n10_ddd",
            "sweep_cbr_split_soft_n10_eee",
        }

    def test_all_keeps_every_ok_ubr_cbr_n10_row(self, fsp, dummy_manifest):
        runs = fsp._load_baseline_runs(
            dummy_manifest, techniques=["UBR", "CBR"], n_reviewers=10, scope="all"
        )
        ids = {rid for rid, _t in runs}
        assert ids == {
            "sweep_ubr_same_n10_aaa",
            "sweep_cbr_same_n10_bbb",
            "sweep_ubr_same_n10_ccc",
            "sweep_ubr_split_soft_n10_ddd",
            "sweep_cbr_split_soft_n10_eee",
        }

    def test_unknown_scope_raises(self, fsp, dummy_manifest):
        with pytest.raises(ValueError):
            fsp._load_baseline_runs(
                dummy_manifest, techniques=["UBR"], n_reviewers=10, scope="nope"
            )


class TestConfigContains:
    def test_substring_filters_by_config_path(self, fsp, dummy_manifest):
        runs = fsp._load_baseline_runs(
            dummy_manifest,
            techniques=["UBR", "CBR"],
            n_reviewers=10,
            scope="all",
            config_contains="split_soft_n10",
        )
        ids = {rid for rid, _t in runs}
        assert ids == {
            "sweep_ubr_split_soft_n10_ddd",
            "sweep_cbr_split_soft_n10_eee",
        }

    def test_substring_unmatched_yields_empty(self, fsp, dummy_manifest):
        runs = fsp._load_baseline_runs(
            dummy_manifest,
            techniques=["UBR", "CBR"],
            n_reviewers=10,
            scope="all",
            config_contains="nonexistent_token",
        )
        assert runs == []


class TestScopeChoicesInCLI:
    def test_argparser_exposes_scope_choices_and_config_contains(self, fsp):
        parser = fsp.build_arg_parser()
        scope_action = next(a for a in parser._actions if "--scope" in a.option_strings)
        assert set(scope_action.choices) == {"same", "split", "all"}
        assert scope_action.default == "same"
        cc_action = next(
            a for a in parser._actions if "--config-contains" in a.option_strings
        )
        assert cc_action.default is None
