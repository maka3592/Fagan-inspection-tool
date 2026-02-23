"""Tests for GoldLoader."""

from pathlib import Path

import pandas as pd
import pytest

from fagan_tool.core.schemas import FaultType, RiskLevel
from fagan_tool.evaluation.gold_loader import GoldLoader


def test_find_header_row_with_meta():
    """Test that header row is found correctly when meta rows exist."""
    # Create a toy dataframe with meta rows (rows = list of column values)
    # Row 0: Meta info
    # Row 1: Meta info
    # Row 2: Header row (should be detected)
    # Row 3+: Data rows
    rows = [
        ["Responsible: TT", "Date: 2025", "Author: XY", ""],
        ["Version: 6.0", "Status: Final", "Notes: xyz", ""],
        ["Position", "Risk", "Type", "Description"],  # <- Header row
        ["2.1", "A", "M", "Missing foo"],
        ["3.2", "B", "W", "Wrong bar"],
    ]
    df_raw = pd.DataFrame(rows)

    # Initialize loader with dummy path
    loader = GoldLoader(Path("dummy.xlsx"))

    # Test header finding
    header_idx = loader._find_header_row(df_raw)

    assert header_idx is not None, "Header row should be found"
    assert header_idx == 2, f"Header should be at index 2, got {header_idx}"

    # Verify the header row contains expected keywords
    header_row = df_raw.iloc[header_idx]
    header_text = " ".join(str(cell).lower() for cell in header_row if pd.notna(cell))
    assert "position" in header_text
    assert "risk" in header_text
    assert "type" in header_text
    assert "description" in header_text


def test_find_header_row_no_meta():
    """Test that header row is found when it's the first row."""
    rows = [
        ["Position", "Risk", "Type", "Description"],  # Header row
        ["2.1", "A", "M", "Missing foo"],
        ["3.2", "B", "W", "Wrong bar"],
    ]
    df_raw = pd.DataFrame(rows)

    loader = GoldLoader(Path("dummy.xlsx"))
    header_idx = loader._find_header_row(df_raw)

    assert header_idx is not None
    assert header_idx == 0, "Header should be at index 0"


def test_find_header_row_not_found():
    """Test that None is returned when no header row exists."""
    # Create dataframe with no recognizable header
    rows = [
        ["foo", "bar", "baz"],
        ["123", "456", "789"],
        ["abc", "def", "ghi"],
    ]
    df_raw = pd.DataFrame(rows)

    loader = GoldLoader(Path("dummy.xlsx"))
    header_idx = loader._find_header_row(df_raw)

    assert header_idx is None, "Should return None when no header found"


def test_cleanup_dataframe():
    """Test that cleanup removes empty columns and rows."""
    # Create dataframe with unnamed columns and empty rows
    df = pd.DataFrame({
        "Position": ["2.1", None, "3.2", None],
        "Description": ["Defect A", None, None, "Defect B"],
        "Unnamed: 0": [None, None, None, None],
        "Risk": ["A", None, "B", None],
    })

    loader = GoldLoader(Path("dummy.xlsx"))
    cleaned = loader._cleanup_dataframe(df)

    # Unnamed column should be removed
    assert "Unnamed: 0" not in cleaned.columns

    # Empty rows (where both position and description are None) should be removed
    # Row 1 and 2 should be removed (both position and description are None or at least one is None)
    # Only rows with valid position or description should remain
    assert len(cleaned) < len(df), "Empty rows should be removed"


def test_load_with_meta_rows(tmp_path):
    """Integration test: load Excel with meta rows."""
    # Create a temporary Excel file with meta rows
    excel_path = tmp_path / "test_gold.xlsx"

    # Build dataframe with meta rows
    rows = [
        ["Responsible: TT", "Version: 6.0", "", ""],
        ["Date: 2025", "Status: Final", "", ""],
        ["Position", "Risk", "Type", "Description"],
        ["2.1", "A", "M", "Missing component X"],
        ["3.2", "B", "W", "Wrong calculation in Y"],
    ]

    df_raw = pd.DataFrame(rows)
    df_raw.to_excel(excel_path, index=False, header=False, engine="openpyxl")

    # Load using GoldLoader
    loader = GoldLoader(excel_path)
    defects = loader.load()

    # Should find 2 defects (rows 3 and 4, after header at row 2)
    assert len(defects) == 2, f"Expected 2 defects, got {len(defects)}"

    # Check first defect
    assert defects[0].position == "2.1"
    assert defects[0].risk.value == "A"
    assert defects[0].fault_type.value == "M"
    assert "Missing component X" in defects[0].description

    # Check second defect
    assert defects[1].position == "3.2"
    assert defects[1].risk.value == "B"
    assert defects[1].fault_type.value == "W"
    assert "Wrong calculation in Y" in defects[1].description


def test_load_no_header_raises(tmp_path):
    """Test that loading without valid header raises ValueError."""
    excel_path = tmp_path / "test_no_header.xlsx"

    # Create Excel with no recognizable header
    rows = [
        ["foo", "bar", "baz"],
        ["123", "456", "789"],
    ]
    df_raw = pd.DataFrame(rows)
    df_raw.to_excel(excel_path, index=False, header=False, engine="openpyxl")

    loader = GoldLoader(excel_path)

    with pytest.raises(ValueError, match="Cannot find header row"):
        loader.load()


def test_column_mapping_fuzzy(tmp_path):
    """Test that fuzzy column mapping works with non-standard names."""
    excel_path = tmp_path / "test_fuzzy_cols.xlsx"

    # Create Excel with non-standard column names
    rows = [
        ["Item Number", "Severity Level", "Fault Class", "Problem Description"],
        ["UC-2.1", "Risk A", "M", "Component X is missing"],
        ["Table-3.2", "Risk B", "W", "Calculation error in Y"],
    ]

    df_raw = pd.DataFrame(rows)
    df_raw.to_excel(excel_path, index=False, header=False, engine="openpyxl")

    loader = GoldLoader(excel_path)
    defects = loader.load()

    # Should find 2 defects with proper mapping
    assert len(defects) == 2

    # Check that position is NOT "unknown"
    assert defects[0].position != "unknown", f"Position should be mapped, got: {defects[0].position}"
    assert "2.1" in defects[0].position or "UC" in defects[0].position

    # Check that description is NOT empty
    assert defects[0].description != "", "Description should be mapped"
    assert "missing" in defects[0].description.lower()

    # Check that risk is properly mapped (not UNK)
    assert defects[0].risk.value == "A", f"Risk should be A, got: {defects[0].risk.value}"

    # Check that fault_type is properly mapped (not UNK)
    assert defects[0].fault_type.value == "M", f"Fault type should be M, got: {defects[0].fault_type.value}"


def test_column_mapping_validation(tmp_path):
    """Test that validation fails when description column is missing."""
    excel_path = tmp_path / "test_no_desc.xlsx"

    # Create Excel with columns that can be detected as header but no description
    # Need at least 2 keywords from header detection to be recognized as header
    rows = [
        ["Item", "Section", "Priority"],  # "Item" matches position patterns
        ["1", "2.1", "High"],
        ["2", "3.2", "Medium"],
    ]

    df_raw = pd.DataFrame(rows)
    df_raw.to_excel(excel_path, index=False, header=False, engine="openpyxl")

    loader = GoldLoader(excel_path)

    # Should raise ValueError about missing description column
    with pytest.raises(ValueError) as exc_info:
        loader.load()

    # Check that error message mentions description
    assert "description" in str(exc_info.value).lower()


def test_normalize_risk_variants():
    """Test that risk normalization handles various formats."""
    loader = GoldLoader(Path("dummy.xlsx"))

    # Test various risk formats
    assert loader._normalize_risk("A") == RiskLevel.A
    assert loader._normalize_risk("Risk A") == RiskLevel.A
    assert loader._normalize_risk("a") == RiskLevel.A
    assert loader._normalize_risk("High") == RiskLevel.A
    assert loader._normalize_risk("1") == RiskLevel.A

    assert loader._normalize_risk("B") == RiskLevel.B
    assert loader._normalize_risk("Risk B") == RiskLevel.B
    assert loader._normalize_risk("Medium") == RiskLevel.B
    assert loader._normalize_risk("2") == RiskLevel.B

    assert loader._normalize_risk("C") == RiskLevel.C
    assert loader._normalize_risk("Risk C") == RiskLevel.C
    assert loader._normalize_risk("Low") == RiskLevel.C
    assert loader._normalize_risk("3") == RiskLevel.C

    assert loader._normalize_risk("") == RiskLevel.UNK
    assert loader._normalize_risk("Unknown") == RiskLevel.UNK


def test_normalize_fault_type_variants():
    """Test that fault type normalization handles various formats."""
    loader = GoldLoader(Path("dummy.xlsx"))

    # Test various fault type formats
    assert loader._normalize_fault_type("M") == FaultType.M
    assert loader._normalize_fault_type("m") == FaultType.M
    assert loader._normalize_fault_type("Missing") == FaultType.M

    assert loader._normalize_fault_type("W") == FaultType.W
    assert loader._normalize_fault_type("w") == FaultType.W
    assert loader._normalize_fault_type("Wrong") == FaultType.W
    assert loader._normalize_fault_type("Incorrect") == FaultType.W

    assert loader._normalize_fault_type("") == FaultType.UNK
    assert loader._normalize_fault_type("Unknown") == FaultType.UNK


def test_filter_meta_comment_rows(tmp_path):
    """Test that meta/comment rows are filtered out."""
    excel_path = tmp_path / "test_filter_meta.xlsx"

    # Create Excel with:
    # - Header row
    # - Intro/comment row with short description
    # - Valid defect row with proper number and description
    # - Another invalid row with description < 10 chars
    rows = [
        ["Number", "Position", "Risk", "Type", "Description"],  # Header
        ["", "", "", "", "The below faults are listed"],  # Should be filtered (intro)
        ["1", "Section 2.1", "A", "M", "Missing error handling in authentication module"],  # Valid
        ["", "", "B", "W", "Short"],  # Should be filtered (short description)
        ["2", "Section 3.2", "B", "W", "Wrong calculation of total price in checkout process"],  # Valid
    ]

    df_raw = pd.DataFrame(rows)
    df_raw.to_excel(excel_path, index=False, header=False, engine="openpyxl")

    # Load using GoldLoader
    loader = GoldLoader(excel_path)
    defects = loader.load()

    # Should only find 2 valid defects (rows 2 and 4, 0-indexed from data rows)
    assert len(defects) == 2, f"Expected 2 defects, got {len(defects)}"

    # Check first valid defect
    assert defects[0].id == "1" or "1" in defects[0].id
    assert "authentication" in defects[0].description.lower()
    assert defects[0].position != "unknown"
    assert len(defects[0].description) > 10

    # Check second valid defect
    assert defects[1].id == "2" or "2" in defects[1].id
    assert "checkout" in defects[1].description.lower()
    assert defects[1].position != "unknown"
    assert len(defects[1].description) > 10


def test_filter_only_unknown_positions(tmp_path):
    """Test that rows with only 'unknown' position are filtered."""
    excel_path = tmp_path / "test_filter_unknown.xlsx"

    rows = [
        ["Number", "Position", "Risk", "Description"],  # Header (need 3+ keywords)
        ["1", "unknown", "A", "This description is long enough but position is unknown"],  # Should be filtered
        ["2", "Section 1.2", "B", "Valid defect with proper position identifier and description"],  # Valid
    ]

    df_raw = pd.DataFrame(rows)
    df_raw.to_excel(excel_path, index=False, header=False, engine="openpyxl")

    loader = GoldLoader(excel_path)
    defects = loader.load()

    # Should only find 1 valid defect
    assert len(defects) == 1, f"Expected 1 defect, got {len(defects)}"
    assert defects[0].position != "unknown"
    assert "Section 1.2" in defects[0].position


def test_gold_defect_id_from_number_column(tmp_path):
    """Test that gold defect IDs are extracted from Number column."""
    excel_path = tmp_path / "test_number_ids.xlsx"

    # Create Excel with Number column containing defect IDs
    rows = [
        ["Number", "Position", "Risk", "Type", "Description"],  # Header
        ["38", "Section 4.1", "A", "M", "Defect 38 with proper number ID"],
        ["42", "Section 5.2", "B", "W", "Defect 42 with another number ID"],
        ["15", "Section 2.3", "C", "M", "Defect 15 to test ordering"],
    ]

    df_raw = pd.DataFrame(rows)
    df_raw.to_excel(excel_path, index=False, header=False, engine="openpyxl")

    loader = GoldLoader(excel_path)
    defects = loader.load()

    # Should find 3 defects
    assert len(defects) == 3, f"Expected 3 defects, got {len(defects)}"

    # Check IDs match the Number column
    ids = [d.id for d in defects]
    assert "38" in ids, "ID '38' should be present"
    assert "42" in ids, "ID '42' should be present"
    assert "15" in ids, "ID '15' should be present"

    # Check specific defect properties
    defect_38 = [d for d in defects if d.id == "38"][0]
    assert defect_38.position == "Section 4.1"
    assert "Defect 38" in defect_38.description


def test_gold_defect_id_with_float_numbers(tmp_path):
    """Test that float numbers (like 1.0) are converted to integers."""
    excel_path = tmp_path / "test_float_numbers.xlsx"

    # Excel may store integers as floats (1.0 instead of 1)
    rows = [
        ["Number", "Position", "Risk", "Type", "Description"],
        [1.0, "Section 1.1", "A", "M", "Defect with float number 1.0"],
        [2.0, "Section 1.2", "B", "W", "Defect with float number 2.0"],
        [10.0, "Section 2.1", "C", "M", "Defect with float number 10.0"],
    ]

    df_raw = pd.DataFrame(rows)
    df_raw.to_excel(excel_path, index=False, header=False, engine="openpyxl")

    loader = GoldLoader(excel_path)
    defects = loader.load()

    assert len(defects) == 3

    # IDs should be clean integers (not "1.0")
    ids = [d.id for d in defects]
    assert "1" in ids, "ID should be '1' not '1.0'"
    assert "2" in ids, "ID should be '2' not '2.0'"
    assert "10" in ids, "ID should be '10' not '10.0'"

    # Should not contain float representations
    assert "1.0" not in ids
    assert "2.0" not in ids


def test_gold_defect_duplicate_ids_warning(tmp_path, caplog):
    """Test that duplicate IDs generate a warning."""
    excel_path = tmp_path / "test_duplicate_ids.xlsx"

    # Create Excel with duplicate Number values
    rows = [
        ["Number", "Position", "Risk", "Type", "Description"],
        ["5", "Section 1.1", "A", "M", "First defect with ID 5"],
        ["5", "Section 2.1", "B", "W", "Second defect with duplicate ID 5"],
        ["6", "Section 3.1", "C", "M", "Unique defect with ID 6"],
    ]

    df_raw = pd.DataFrame(rows)
    df_raw.to_excel(excel_path, index=False, header=False, engine="openpyxl")

    loader = GoldLoader(excel_path)

    import logging
    with caplog.at_level(logging.ERROR):
        defects = loader.load()

    # Should still load all defects
    assert len(defects) == 3

    # Should have logged an error about duplicate ID
    error_logs = [record.message for record in caplog.records if record.levelname == "ERROR"]
    assert any("Duplicate ID '5'" in msg for msg in error_logs), "Should warn about duplicate ID '5'"
