"""Tests for LeakageGuard."""

import pytest
from pathlib import Path
from fagan_tool.utils.leakage_guard import LeakageGuard


def test_validate_safe_path():
    """Test that safe paths are allowed."""
    safe_paths = [
        "artifacts/input/design/doc.pdf",
        "artifacts/input/usecases/uc.pdf",
        Path("configs/example.yaml"),
    ]

    for path in safe_paths:
        assert LeakageGuard.validate_path(path)


def test_validate_gold_path_raises():
    """Test that gold paths raise ValueError."""
    gold_paths = [
        "artifacts/gold/faults.xls",
        "gold/faults_list.xls",
        Path("artifacts/gold/reference.xlsx"),
    ]

    for path in gold_paths:
        with pytest.raises(ValueError, match="LEAKAGE GUARD"):
            LeakageGuard.validate_path(path)


def test_validate_forbidden_filename_raises():
    """Test that forbidden filenames raise ValueError."""
    forbidden_paths = [
        "data/Faults_List_In_ver6.xls",
        "temp/ground_truth.json",
        Path("backup/gold_standard.csv"),
    ]

    for path in forbidden_paths:
        with pytest.raises(ValueError, match="LEAKAGE GUARD"):
            LeakageGuard.validate_path(path)


def test_validate_multiple_paths():
    """Test validation of multiple paths."""
    safe_paths = [
        "artifacts/input/design/doc1.pdf",
        "artifacts/input/design/doc2.pdf",
    ]

    assert LeakageGuard.validate_paths(safe_paths)

    # Mix of safe and unsafe should raise
    mixed_paths = safe_paths + ["artifacts/gold/unsafe.xls"]
    with pytest.raises(ValueError):
        LeakageGuard.validate_paths(mixed_paths)


def test_is_gold_path():
    """Test non-raising check for gold paths."""
    assert LeakageGuard.is_gold_path("artifacts/gold/file.xls")
    assert LeakageGuard.is_gold_path(Path("gold/file.xls"))
    assert not LeakageGuard.is_gold_path("artifacts/input/file.pdf")
