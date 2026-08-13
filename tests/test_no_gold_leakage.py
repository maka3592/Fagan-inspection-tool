"""End-to-end proof that the inspection RUN does not depend on the gold file.

These tests verify three claims that together rule out gold-standard
leakage from the run/reviewer/meeting pipeline:

1. ``fagan run`` (loader + dry-run pipeline) works when the gold Excel
   file is temporarily removed from ``artifacts/gold/``.
2. ``fagan eval`` fails cleanly with ``FileNotFoundError`` when the gold
   file is missing — proving gold is exclusively an evaluation input.
3. The gold file is byte-identical (SHA-256) before and after the test
   sequence — nothing in the run/eval flow rewrites or normalises it.

The tests temporarily relocate the gold file to a pytest tmpdir, run the
checks, and restore the original file under a ``finally`` block so the
repository state is identical on success *and* on failure.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Iterator, Tuple

import pytest

from fagan_tool.cli import load_config
from fagan_tool.core.process import FaganProcess
from fagan_tool.evaluation import GoldLoader
from fagan_tool.utils.artifact_loader import ArtifactLoader
from fagan_tool.utils.leakage_guard import LeakageGuard


REPO_ROOT = Path(__file__).resolve().parents[1]
GOLD_DIR = REPO_ROOT / "artifacts" / "gold"
GOLD_XLS = GOLD_DIR / "Faults_List_In_ver6.xls"
GOLD_README = GOLD_DIR / "README.md"
EXAMPLE_CONFIG = REPO_ROOT / "configs" / "examples" / "c1_ubr.yaml"


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


@pytest.fixture
def quarantined_gold(tmp_path: Path) -> Iterator[Tuple[str, Path]]:
    """Move the gold Excel out of the repo for the duration of one test.

    Yields ``(sha256_before, quarantine_path)``. Always restores the file
    in a ``finally`` block (so test failures cannot leave gold missing).
    """
    if not GOLD_XLS.exists():
        pytest.skip("Gold file missing at start of test — environment unhealthy.")

    sha_before = _sha256(GOLD_XLS)
    sha_readme_before = _sha256(GOLD_README) if GOLD_README.exists() else None

    quarantine = tmp_path / GOLD_XLS.name
    shutil.move(str(GOLD_XLS), str(quarantine))
    try:
        assert not GOLD_XLS.exists(), "gold quarantine failed — file still in place"
        yield sha_before, quarantine
    finally:
        if not GOLD_XLS.exists():
            shutil.move(str(quarantine), str(GOLD_XLS))
        # Sanity: gold is byte-identical and README untouched
        assert GOLD_XLS.exists(), "gold restoration failed"
        assert _sha256(GOLD_XLS) == sha_before, "gold file was modified during test"
        if sha_readme_before is not None:
            assert _sha256(GOLD_README) == sha_readme_before, (
                "gold README was modified during test"
            )


def test_run_pipeline_loads_no_gold(quarantined_gold, tmp_path: Path):
    """The run pipeline (config + artifacts + UBR validation) must work
    even when the gold file is absent. None of the artifact paths returned
    by ``ArtifactLoader`` may resolve into the gold directory.

    Run output is isolated into the pytest tmpdir: ``FaganProcess.__init__``
    creates its run directory immediately on construction, so without the
    ``output_dir`` override this test would leave empty auto-incremented
    ``runs/test_no_gold_run*`` directories in the real repository.
    """
    cfg = load_config(EXAMPLE_CONFIG)

    repo_runs_before = set((REPO_ROOT / "runs").glob("test_no_gold_run*"))

    process = FaganProcess(
        cfg, output_dir=tmp_path / "runs", run_id_override="test_no_gold_run"
    )
    # This is the very same path the CLI takes inside `fagan run` for UBR.
    process._validate_ubr_config()

    # Isolation guarantee: the run directory lives in the pytest tmpdir,
    # and nothing new appeared under the repository's productive runs/.
    assert process.output_dir == tmp_path / "runs" / "test_no_gold_run", (
        "run output must be created inside the pytest tmpdir"
    )
    assert process.output_dir.is_dir()
    assert set((REPO_ROOT / "runs").glob("test_no_gold_run*")) == repo_runs_before, (
        "test must not create run directories under the repository runs/ folder"
    )

    loader = ArtifactLoader()
    artifacts = loader.load_artifacts(cfg.artifacts)
    assert artifacts, "no input artifacts were loaded for the example config"

    for art in artifacts:
        path = art["metadata"].path
        assert not LeakageGuard.is_gold_path(path), (
            f"run pipeline loaded an artifact from a gold path: {path}"
        )


def test_eval_fails_without_gold(quarantined_gold, tmp_path: Path):
    """``GoldLoader.load()`` (and therefore ``fagan eval``) must raise
    when the gold file is missing — proving gold is mandatory for eval
    only, not for run.
    """
    loader = GoldLoader(GOLD_XLS)
    with pytest.raises(FileNotFoundError):
        loader.load()

    # Cross-check via the CLI: `fagan eval` exits non-zero.
    dummy_run_dir = tmp_path / "dummy_run"
    dummy_run_dir.mkdir()
    # Eval needs a defects file to even reach the GoldLoader.
    (dummy_run_dir / "final_defects.json").write_text(json.dumps([]))

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "fagan_tool.cli",
            "eval",
            "--run",
            dummy_run_dir.name,
            "--gold",
            str(GOLD_XLS),
            "--match-threshold",
            "0.65",
        ],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert completed.returncode != 0, (
        "fagan eval returned 0 with gold missing — leakage barrier broken"
    )


def test_leakage_guard_rejects_gold_paths_independently_of_file_existence():
    """The static guard must reject any path inside the gold directory
    regardless of whether the file is actually present on disk. This
    closes the door on "delete gold, sneak it in via config" attacks.
    """
    forbidden_examples = [
        "artifacts/gold/Faults_List_In_ver6.xls",
        "artifacts/gold/anything.csv",
        "./../gold/secret.xlsx",
    ]
    for p in forbidden_examples:
        with pytest.raises(ValueError, match="LEAKAGE GUARD"):
            LeakageGuard.validate_path(p)
