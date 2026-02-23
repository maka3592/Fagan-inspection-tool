"""Tests for core schemas."""

import pytest
from fagan_tool.core.schemas import (
    Defect,
    FaultType,
    RiskLevel,
    ReadingTechnique,
    ConditionType,
)


def test_defect_creation():
    """Test basic defect creation."""
    defect = Defect(
        id="test_1",
        position="Section 3",
        risk=RiskLevel.A,
        fault_type=FaultType.M,
        description="Test defect",
        evidence="Test evidence (p. 10)",
    )

    assert defect.id == "test_1"
    assert defect.risk == RiskLevel.A
    assert defect.fault_type == FaultType.M
    assert defect.confidence == 0.8  # Default


def test_defect_confidence_validation():
    """Test that confidence must be in valid range [0.0, 1.0]."""
    from pydantic import ValidationError

    # Valid confidence values should work
    defect = Defect(
        id="test_1",
        position="Section 3",
        risk=RiskLevel.B,
        fault_type=FaultType.W,
        description="Test",
        evidence="Evidence",
        confidence=0.9,
    )
    assert defect.confidence == 0.9

    # Invalid confidence (> 1.0) should raise ValidationError
    with pytest.raises(ValidationError):
        Defect(
            id="test_2",
            position="Section 3",
            risk=RiskLevel.B,
            fault_type=FaultType.W,
            description="Test",
            evidence="Evidence",
            confidence=1.5,  # Invalid - too high
        )

    # Invalid confidence (< 0.0) should raise ValidationError
    with pytest.raises(ValidationError):
        Defect(
            id="test_3",
            position="Section 3",
            risk=RiskLevel.B,
            fault_type=FaultType.W,
            description="Test",
            evidence="Evidence",
            confidence=-0.5,  # Invalid - negative
        )


def test_risk_level_enum():
    """Test RiskLevel enum."""
    assert RiskLevel.A.value == "A"
    assert RiskLevel.B.value == "B"
    assert RiskLevel.C.value == "C"
    assert RiskLevel.UNK.value == "UNK"


def test_fault_type_enum():
    """Test FaultType enum."""
    assert FaultType.M.value == "M"
    assert FaultType.W.value == "W"
    assert FaultType.UNK.value == "UNK"


def test_reading_technique_enum():
    """Test ReadingTechnique enum."""
    assert ReadingTechnique.UBR.value == "UBR"
    assert ReadingTechnique.CBR.value == "CBR"
    assert ReadingTechnique.PBR_TESTER.value == "PBR_TESTER"
    assert ReadingTechnique.PBR_DESIGNER.value == "PBR_DESIGNER"
    assert ReadingTechnique.PBR_USER.value == "PBR_USER"


def test_condition_type_enum():
    """Test ConditionType enum."""
    assert ConditionType.C1_UBR.value == "C1_UBR"
    assert ConditionType.C2_CBR.value == "C2_CBR"
    assert ConditionType.C3_PBR_TEAM.value == "C3_PBR_TEAM"
    assert ConditionType.C4_HYBRID.value == "C4_HYBRID"


def test_defect_serialization():
    """Test that defects can be serialized to dict."""
    defect = Defect(
        id="test_1",
        position="Section 3",
        risk=RiskLevel.A,
        fault_type=FaultType.M,
        description="Test defect",
        evidence="Test evidence",
        flags=["uncertain"],
    )

    data = defect.model_dump()

    assert data["id"] == "test_1"
    assert data["risk"] == "A"
    assert data["fault_type"] == "M"
    assert "uncertain" in data["flags"]


def test_evidence_string_normalization():
    """Test that string evidence is normalized to dict."""
    defect = Defect(
        id="test_1",
        position="Section 3",
        risk=RiskLevel.A,
        fault_type=FaultType.M,
        description="Test defect",
        evidence="The system lacks error handling (see page 42)",
    )

    # Evidence should be normalized to dict
    assert isinstance(defect.evidence, dict)
    assert defect.evidence["quote_or_paraphrase"] == "The system lacks error handling (see page 42)"
    assert "page_hint" in defect.evidence


def test_evidence_empty_string_marks_incomplete():
    """Test that empty string evidence marks defect as incomplete."""
    defect = Defect(
        id="test_1",
        position="Section 3",
        risk=RiskLevel.B,
        fault_type=FaultType.W,
        description="Test defect",
        evidence="",  # Empty evidence
    )

    # Evidence should be normalized to dict with empty quote
    assert isinstance(defect.evidence, dict)
    assert defect.evidence["quote_or_paraphrase"] == ""
    assert defect.evidence["page_hint"] is None

    # Should be marked as incomplete
    assert "incomplete" in defect.flags


def test_evidence_dict_preserved():
    """Test that dict evidence is preserved."""
    evidence_dict = {
        "quote_or_paraphrase": "Error handling is missing",
        "page_hint": "p. 42"
    }

    defect = Defect(
        id="test_1",
        position="Section 3",
        risk=RiskLevel.A,
        fault_type=FaultType.M,
        description="Test defect",
        evidence=evidence_dict,
    )

    # Evidence should remain as dict
    assert isinstance(defect.evidence, dict)
    assert defect.evidence["quote_or_paraphrase"] == "Error handling is missing"
    assert defect.evidence["page_hint"] == "p. 42"
    assert "incomplete" not in defect.flags


def test_evidence_dict_with_page_hint():
    """Test that page_hint is used when converting string evidence."""
    defect = Defect(
        id="test_1",
        position="Section 3",
        page_hint="p. 10-12",
        risk=RiskLevel.A,
        fault_type=FaultType.M,
        description="Test defect",
        evidence="Missing validation logic",
    )

    # Evidence should include page_hint from defect
    assert isinstance(defect.evidence, dict)
    assert defect.evidence["quote_or_paraphrase"] == "Missing validation logic"
    assert defect.evidence["page_hint"] == "p. 10-12"


def test_evidence_dict_missing_keys():
    """Test that dict evidence with missing keys is repaired."""
    defect = Defect(
        id="test_1",
        position="Section 3",
        risk=RiskLevel.B,
        fault_type=FaultType.W,
        description="Test defect",
        evidence={"quote": "Some evidence"},  # Missing standard keys
    )

    # Should have standard keys
    assert isinstance(defect.evidence, dict)
    assert "quote_or_paraphrase" in defect.evidence
    assert defect.evidence["quote_or_paraphrase"] == "Some evidence"
    assert "page_hint" in defect.evidence


def test_evidence_dict_empty_marks_incomplete():
    """Test that dict with empty quote marks as incomplete."""
    defect = Defect(
        id="test_1",
        position="Section 3",
        risk=RiskLevel.C,
        fault_type=FaultType.M,
        description="Test defect",
        evidence={"quote_or_paraphrase": "", "page_hint": None},
    )

    # Should be marked as incomplete
    assert "incomplete" in defect.flags


# Point 4: Output standardization tests

def test_defect_empty_position_flagged():
    """Test that empty position is flagged (Point 4 standardization)."""
    defect = Defect(
        id="test_1",
        position="",  # Empty position
        risk=RiskLevel.B,
        fault_type=FaultType.W,
        description="Valid description",
        evidence="Valid evidence",
    )

    assert "missing_position" in defect.flags


def test_defect_unknown_position_flagged():
    """Test that 'unknown' position is flagged (Point 4 standardization)."""
    defect = Defect(
        id="test_1",
        position="unknown",
        risk=RiskLevel.B,
        fault_type=FaultType.W,
        description="Valid description",
        evidence="Valid evidence",
    )

    assert "missing_position" in defect.flags


def test_defect_empty_description_flagged():
    """Test that empty description is flagged as incomplete (Point 4)."""
    defect = Defect(
        id="test_1",
        position="Section 3.2",
        risk=RiskLevel.A,
        fault_type=FaultType.M,
        description="",  # Empty description
        evidence="Valid evidence",
    )

    assert "missing_description" in defect.flags
    assert "incomplete" in defect.flags


def test_defect_valid_fields_no_extra_flags():
    """Test that valid defect doesn't get spurious flags (Point 4)."""
    defect = Defect(
        id="test_1",
        position="Section 3.2",
        risk=RiskLevel.A,
        fault_type=FaultType.M,
        description="'Signal_X': Missing parameter definition",
        evidence="Section 3.2 lacks the parameter (p. 15)",
    )

    # Should not have any missing_* flags
    assert "missing_position" not in defect.flags
    assert "missing_description" not in defect.flags
    assert "incomplete" not in defect.flags


def test_defect_schema_version_exists():
    """Test that DEFECT_SCHEMA_VERSION is defined (Point 4)."""
    from fagan_tool.core.schemas import DEFECT_SCHEMA_VERSION

    assert DEFECT_SCHEMA_VERSION is not None
    assert isinstance(DEFECT_SCHEMA_VERSION, str)
    # Should be semantic version format
    assert "." in DEFECT_SCHEMA_VERSION
