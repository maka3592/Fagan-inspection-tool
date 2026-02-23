"""Tests for scribe agent position validation, dedup rescue, and provenance."""

import pytest
from unittest.mock import MagicMock, patch

from fagan_tool.agents.scribe_agent import DEDUP_SIMILARITY_THRESHOLD, PROVENANCE_MAPPING_THRESHOLD, ScribeAgent
from fagan_tool.core.schemas import Defect, DuplicateGroup, FaultType, ReadingTechnique, ReviewerOutput, RiskLevel


class TestScribePositionValidation:
    """Tests for position token validation in scribe consolidation."""

    @pytest.fixture
    def scribe_agent(self, tmp_path):
        """Create scribe agent with mock provider."""
        mock_provider = MagicMock()
        prompt_dir = tmp_path / "prompts"
        prompt_dir.mkdir()
        (prompt_dir / "scribe_meeting.txt").write_text("Test prompt")
        return ScribeAgent(mock_provider, prompt_dir)

    def test_section_position_accepted(self, scribe_agent):
        """Valid section position is accepted."""
        defect_data = {
            "position": "Section 4.1",
            "page_hint": "p. 7",
            "description": "Missing signal definition",
            "evidence": "The diagram shows...",
            "risk": "A",
            "fault_type": "M",
        }
        result = scribe_agent._validate_defect_completeness(defect_data)
        assert result["is_complete"] is True

    def test_section_position_canonicalized(self, scribe_agent):
        """Section with prefix gets position accepted (canonicalized downstream)."""
        defect_data = {
            "position": "Section 3.4.1",
            "page_hint": "p. 10",
            "description": "Wrong parameter type",
            "evidence": "Parameter X is defined as...",
            "risk": "B",
            "fault_type": "W",
        }
        result = scribe_agent._validate_defect_completeness(defect_data)
        assert result["is_complete"] is True

    def test_table_position_accepted(self, scribe_agent):
        """Table reference is accepted."""
        defect_data = {
            "position": "Table 1",
            "page_hint": "p. 5",
            "description": "Missing column",
            "evidence": "Table 1 lacks...",
            "risk": "B",
            "fault_type": "M",
        }
        result = scribe_agent._validate_defect_completeness(defect_data)
        assert result["is_complete"] is True

    def test_use_case_only_rejected(self, scribe_agent):
        """Use Case without section reference is rejected."""
        defect_data = {
            "position": "Use Case 1.1",
            "page_hint": "p. 3",
            "description": "Missing step",
            "evidence": "Use Case 1.1 doesn't...",
            "risk": "C",
            "fault_type": "M",
        }
        result = scribe_agent._validate_defect_completeness(defect_data)
        assert result["is_complete"] is False
        assert "use case" in result["reason"].lower() or "no valid" in result["reason"].lower()

    def test_invalid_position_no_tokens_rejected(self, scribe_agent):
        """Position without valid tokens is rejected."""
        defect_data = {
            "position": "Overview section",
            "page_hint": "p. 2",
            "description": "Missing overview",
            "evidence": "The overview...",
            "risk": "C",
            "fault_type": "M",
        }
        result = scribe_agent._validate_defect_completeness(defect_data)
        assert result["is_complete"] is False
        assert "no valid" in result["reason"].lower()

    def test_combined_table_section_accepted(self, scribe_agent):
        """Combined table and section reference is accepted."""
        defect_data = {
            "position": "Table 1, 3.4.2",
            "page_hint": "p. 8",
            "description": "Signal mismatch",
            "evidence": "Table 1 defines X but 3.4.2 uses Y",
            "risk": "A",
            "fault_type": "W",
        }
        result = scribe_agent._validate_defect_completeness(defect_data)
        assert result["is_complete"] is True

    def test_missing_risk_rejected(self, scribe_agent):
        """Missing risk field is rejected."""
        defect_data = {
            "position": "3.4.1",
            "page_hint": "p. 7",
            "description": "Missing signal",
            "evidence": "The diagram...",
            "risk": "UNK",
            "fault_type": "M",
        }
        result = scribe_agent._validate_defect_completeness(defect_data)
        assert result["is_complete"] is False
        assert "risk" in result["reason"].lower()


class TestScribePositionCanonicalization:
    """Tests for position canonicalization during consolidation."""

    @pytest.fixture
    def scribe_agent(self, tmp_path):
        """Create scribe agent with mock provider."""
        mock_provider = MagicMock()
        prompt_dir = tmp_path / "prompts"
        prompt_dir.mkdir()
        (prompt_dir / "scribe_meeting.txt").write_text("Test prompt")
        return ScribeAgent(mock_provider, prompt_dir)

    def test_consolidate_canonicalizes_positions(self, scribe_agent):
        """Consolidation canonicalizes position tokens."""
        # Mock the LLM response
        mock_response = """
        {
            "consolidated_defects": [
                {
                    "position": "Section 3.4.1",
                    "page_hint": "p. 7",
                    "description": "Missing signal",
                    "evidence": "The diagram shows...",
                    "risk": "A",
                    "fault_type": "M",
                    "confidence": 0.9,
                    "flags": []
                }
            ],
            "duplicates_removed": 0,
            "conflicts_flagged": 0,
            "minutes": "Test meeting",
            "exit_decision": "Accept"
        }
        """
        scribe_agent.call_llm = MagicMock(return_value=mock_response)

        # Create minimal reviewer output
        reviewer_output = ReviewerOutput(
            reviewer_id="test",
            technique=ReadingTechnique.UBR,
            defects=[],
            notes="",
        )

        result = scribe_agent.consolidate([reviewer_output])

        # Position should be canonicalized (no "Section" prefix)
        assert len(result.consolidated_defects) == 1
        assert result.consolidated_defects[0].position == "3.4.1"


class TestScribeDedupRescue:
    """Tests for _validate_and_rescue dedup protection."""

    @pytest.fixture
    def scribe_agent(self, tmp_path):
        """Create scribe agent with mock provider."""
        mock_provider = MagicMock()
        prompt_dir = tmp_path / "prompts"
        prompt_dir.mkdir()
        (prompt_dir / "scribe_meeting.txt").write_text("Test prompt")
        return ScribeAgent(mock_provider, prompt_dir)

    def _make_defect(self, position, description, confidence=0.85, risk="A", fault_type="M", defect_id="test"):
        """Helper to create a Defect."""
        return Defect(
            id=defect_id,
            position=position,
            page_hint="p. 5",
            risk=RiskLevel(risk),
            fault_type=FaultType(fault_type),
            description=description,
            evidence="Test evidence",
            confidence=confidence,
        )

    def _make_reviewer_output(self, defects):
        """Helper to create a ReviewerOutput."""
        return ReviewerOutput(
            reviewer_id="test_reviewer",
            technique=ReadingTechnique.UBR,
            defects=defects,
            notes="",
        )

    def test_no_rescue_when_all_represented(self, scribe_agent):
        """No defects rescued when all reviewer defects match consolidated."""
        consolidated = [
            self._make_defect("3.4.1", "Missing signal Ack in MSC diagram", defect_id="meeting_1"),
        ]
        reviewer_outputs = [
            self._make_reviewer_output([
                self._make_defect("3.4.1", "Missing signal Ack in MSC diagram", defect_id="r1_1"),
            ])
        ]

        result, count = scribe_agent._validate_and_rescue(consolidated, reviewer_outputs)
        assert count == 0
        assert len(result) == 1

    def test_rescue_distinct_defect_same_position(self, scribe_agent):
        """Rescue distinct defect at same position that LLM incorrectly merged."""
        consolidated = [
            self._make_defect("3.4.1", "Missing signal Ack in MSC diagram", defect_id="meeting_1"),
        ]
        reviewer_outputs = [
            self._make_reviewer_output([
                self._make_defect("3.4.1", "Missing signal Ack in MSC diagram", defect_id="r1_1"),
                self._make_defect("3.4.1", "Missing timeout handling for voice communication", defect_id="r1_2"),
            ])
        ]

        result, count = scribe_agent._validate_and_rescue(consolidated, reviewer_outputs)
        assert count == 1  # One defect rescued
        assert len(result) == 2  # Original + rescued
        descriptions = {d.description for d in result}
        assert "Missing timeout handling for voice communication" in descriptions

    def test_no_rescue_for_true_duplicates(self, scribe_agent):
        """Don't rescue defects that are true duplicates of consolidated ones."""
        consolidated = [
            self._make_defect("3.4.1", "Missing signal Ack in MSC diagram", defect_id="meeting_1"),
        ]
        reviewer_outputs = [
            self._make_reviewer_output([
                self._make_defect("3.4.1", "Missing signal Ack in the MSC diagram", defect_id="r1_1"),
                self._make_defect("3.4.1", "Signal Ack is missing from MSC diagram", defect_id="r2_1"),
            ])
        ]

        result, count = scribe_agent._validate_and_rescue(consolidated, reviewer_outputs)
        assert count == 0  # All are duplicates of the consolidated one
        assert len(result) == 1

    def test_rescue_defect_different_position(self, scribe_agent):
        """Rescue defect at different position not in consolidated."""
        consolidated = [
            self._make_defect("3.4.1", "Missing signal Ack", defect_id="meeting_1"),
        ]
        reviewer_outputs = [
            self._make_reviewer_output([
                self._make_defect("3.4.1", "Missing signal Ack", defect_id="r1_1"),
                self._make_defect("4.2", "Missing Stop_Voice signal in MSC", defect_id="r1_2"),
            ])
        ]

        result, count = scribe_agent._validate_and_rescue(consolidated, reviewer_outputs)
        assert count == 1
        assert len(result) == 2
        positions = {d.position for d in result}
        assert "4.2" in positions

    def test_no_duplicate_rescues(self, scribe_agent):
        """Same distinct defect from multiple reviewers rescued only once."""
        consolidated = [
            self._make_defect("3.4.1", "Missing signal Ack", defect_id="meeting_1"),
        ]
        reviewer_outputs = [
            self._make_reviewer_output([
                self._make_defect("3.4.1", "Missing timeout for voice communication", defect_id="r1_1"),
            ]),
            self._make_reviewer_output([
                self._make_defect("3.4.1", "Missing timeout handling for voice communication", defect_id="r2_1"),
            ]),
        ]

        result, count = scribe_agent._validate_and_rescue(consolidated, reviewer_outputs)
        # Both reviewers found the same distinct defect - should only be rescued once
        assert count == 1
        assert len(result) == 2

    def test_rescue_multiple_distinct_at_same_position(self, scribe_agent):
        """Multiple distinct defects at same position all rescued."""
        consolidated = [
            self._make_defect("3.4.1", "Missing signal Ack in MSC", defect_id="meeting_1"),
        ]
        reviewer_outputs = [
            self._make_reviewer_output([
                self._make_defect("3.4.1", "Missing timeout handling for voice signals", defect_id="r1_1"),
                self._make_defect("3.4.1", "Signal Voice_msg is missing from the diagram", defect_id="r1_2"),
            ])
        ]

        result, count = scribe_agent._validate_and_rescue(consolidated, reviewer_outputs)
        assert count == 2  # Both distinct defects rescued
        assert len(result) == 3  # 1 consolidated + 2 rescued

    def test_rescued_defect_has_meeting_id(self, scribe_agent):
        """Rescued defects get new meeting_ IDs."""
        consolidated = []
        reviewer_outputs = [
            self._make_reviewer_output([
                self._make_defect("3.4.1", "Missing signal Ack", defect_id="r1_1"),
            ])
        ]

        result, count = scribe_agent._validate_and_rescue(consolidated, reviewer_outputs)
        assert count == 1
        assert result[0].id.startswith("meeting_")

    def test_rescued_defect_position_canonicalized(self, scribe_agent):
        """Rescued defects have canonicalized positions."""
        consolidated = []
        reviewer_outputs = [
            self._make_reviewer_output([
                self._make_defect("Section 3.4.1", "Missing signal Ack", defect_id="r1_1"),
            ])
        ]

        result, count = scribe_agent._validate_and_rescue(consolidated, reviewer_outputs)
        assert count == 1
        assert result[0].position == "3.4.1"  # Canonicalized

    def test_invalid_position_not_rescued(self, scribe_agent):
        """Defects with invalid positions are not rescued."""
        consolidated = []
        reviewer_outputs = [
            self._make_reviewer_output([
                self._make_defect("Overview", "Missing overview section", defect_id="r1_1"),
            ])
        ]

        result, count = scribe_agent._validate_and_rescue(consolidated, reviewer_outputs)
        assert count == 0
        assert len(result) == 0

    def test_threshold_constant_exported(self):
        """DEDUP_SIMILARITY_THRESHOLD is accessible and set to 0.85."""
        assert DEDUP_SIMILARITY_THRESHOLD == 0.85


class TestScribeProvenance:
    """Tests for provenance mapping in scribe consolidation."""

    @pytest.fixture
    def scribe_agent(self, tmp_path):
        """Create scribe agent with mock provider."""
        mock_provider = MagicMock()
        prompt_dir = tmp_path / "prompts"
        prompt_dir.mkdir()
        (prompt_dir / "scribe_meeting.txt").write_text("Test prompt")
        return ScribeAgent(mock_provider, prompt_dir)

    def _make_defect(self, position, description, confidence=0.85, risk="A",
                     fault_type="M", defect_id="test", reviewer_id=None,
                     technique=None):
        """Helper to create a Defect."""
        return Defect(
            id=defect_id,
            position=position,
            page_hint="p. 5",
            risk=RiskLevel(risk),
            fault_type=FaultType(fault_type),
            description=description,
            evidence="Test evidence",
            confidence=confidence,
            reviewer_id=reviewer_id,
            technique=technique,
        )

    def _make_reviewer_output(self, defects, reviewer_id="test_reviewer",
                              technique=ReadingTechnique.UBR):
        """Helper to create a ReviewerOutput."""
        return ReviewerOutput(
            reviewer_id=reviewer_id,
            technique=technique,
            defects=defects,
            notes="",
        )

    def test_map_provenance_single_source(self, scribe_agent):
        """Consolidated defect maps to single source reviewer defect."""
        consolidated = [
            self._make_defect(
                "3.4.1", "Missing signal Ack in MSC diagram",
                defect_id="meeting_1",
            ),
        ]
        reviewer_outputs = [
            self._make_reviewer_output(
                [
                    self._make_defect(
                        "3.4.1", "Missing signal Ack in MSC diagram",
                        defect_id="r1_1", reviewer_id="reviewer_1",
                        technique=ReadingTechnique.UBR,
                    ),
                ],
                reviewer_id="reviewer_1",
            ),
        ]

        scribe_agent._map_provenance(consolidated, reviewer_outputs)

        assert consolidated[0].source_defect_ids == ["r1_1"]
        assert consolidated[0].source_reviewer_ids == ["reviewer_1"]
        assert consolidated[0].source_techniques == ["UBR"]

    def test_map_provenance_multiple_sources(self, scribe_agent):
        """Consolidated defect maps to multiple source reviewer defects."""
        consolidated = [
            self._make_defect(
                "3.4.1", "Missing signal Ack in MSC diagram",
                defect_id="meeting_1",
            ),
        ]
        reviewer_outputs = [
            self._make_reviewer_output(
                [
                    self._make_defect(
                        "3.4.1", "Missing signal Ack in MSC diagram",
                        defect_id="r1_1", reviewer_id="reviewer_1",
                        technique=ReadingTechnique.UBR,
                    ),
                ],
                reviewer_id="reviewer_1",
            ),
            self._make_reviewer_output(
                [
                    self._make_defect(
                        "3.4.1", "Signal Ack is missing from MSC diagram",
                        defect_id="r2_1", reviewer_id="reviewer_2",
                        technique=ReadingTechnique.UBR,
                    ),
                ],
                reviewer_id="reviewer_2",
            ),
        ]

        scribe_agent._map_provenance(consolidated, reviewer_outputs)

        assert "r1_1" in consolidated[0].source_defect_ids
        assert "r2_1" in consolidated[0].source_defect_ids
        assert "reviewer_1" in consolidated[0].source_reviewer_ids
        assert "reviewer_2" in consolidated[0].source_reviewer_ids

    def test_map_provenance_skips_already_set(self, scribe_agent):
        """Provenance is not overwritten on rescued defects."""
        consolidated = [
            self._make_defect(
                "3.4.1", "Missing signal Ack",
                defect_id="meeting_1",
            ),
        ]
        # Pre-set provenance (as if rescued)
        consolidated[0].source_defect_ids = ["r1_1"]
        consolidated[0].source_reviewer_ids = ["reviewer_1"]
        consolidated[0].source_techniques = ["UBR"]

        reviewer_outputs = [
            self._make_reviewer_output(
                [
                    self._make_defect(
                        "3.4.1", "Missing signal Ack",
                        defect_id="r1_1", reviewer_id="reviewer_1",
                    ),
                ],
            ),
        ]

        scribe_agent._map_provenance(consolidated, reviewer_outputs)

        # Should NOT be overwritten
        assert consolidated[0].source_defect_ids == ["r1_1"]

    def test_build_duplicate_groups(self, scribe_agent):
        """Duplicate groups built from provenance."""
        consolidated = [
            self._make_defect(
                "3.4.1", "Missing signal 'Ack' in MSC diagram",
                defect_id="meeting_1",
            ),
        ]
        consolidated[0].source_defect_ids = ["r1_1", "r2_1"]

        groups = scribe_agent._build_duplicate_groups(consolidated)

        assert len(groups) == 1
        assert groups[0].canonical_id == "meeting_1"
        assert groups[0].merged_ids == ["r1_1", "r2_1"]
        assert len(groups[0].position_tokens) > 0

    def test_no_duplicate_groups_single_source(self, scribe_agent):
        """No duplicate group when only one source."""
        consolidated = [
            self._make_defect("3.4.1", "Missing signal Ack", defect_id="meeting_1"),
        ]
        consolidated[0].source_defect_ids = ["r1_1"]

        groups = scribe_agent._build_duplicate_groups(consolidated)

        assert len(groups) == 0

    def test_duplicates_removed_from_groups(self, scribe_agent):
        """duplicates_removed is computed from duplicate_groups."""
        consolidated = [
            self._make_defect("3.4.1", "Missing signal 'Ack'", defect_id="meeting_1"),
            self._make_defect("4.2", "Missing 'Stop_Voice'", defect_id="meeting_2"),
        ]
        consolidated[0].source_defect_ids = ["r1_1", "r2_1", "r3_1"]  # 3 sources → 2 removed
        consolidated[1].source_defect_ids = ["r1_2", "r2_2"]  # 2 sources → 1 removed

        groups = scribe_agent._build_duplicate_groups(consolidated)

        duplicates_removed = sum(len(g.merged_ids) - 1 for g in groups)
        assert duplicates_removed == 3  # (3-1) + (2-1) = 3

    def test_detect_conflicts_risk(self, scribe_agent):
        """Conflicts detected when source defects disagree on risk."""
        consolidated = [
            self._make_defect("3.4.1", "Missing signal Ack", defect_id="meeting_1"),
        ]
        consolidated[0].source_defect_ids = ["r1_1", "r2_1"]

        reviewer_outputs = [
            self._make_reviewer_output(
                [self._make_defect("3.4.1", "Missing signal Ack",
                                   defect_id="r1_1", risk="A")],
                reviewer_id="reviewer_1",
            ),
            self._make_reviewer_output(
                [self._make_defect("3.4.1", "Signal Ack missing",
                                   defect_id="r2_1", risk="B")],
                reviewer_id="reviewer_2",
            ),
        ]

        conflicts = scribe_agent._detect_conflicts(consolidated, reviewer_outputs)

        assert len(conflicts) >= 1
        assert any(c.field == "risk" for c in conflicts)

    def test_provenance_threshold_constant(self):
        """PROVENANCE_MAPPING_THRESHOLD is accessible."""
        assert PROVENANCE_MAPPING_THRESHOLD == 0.50

    def test_rescued_defect_has_provenance(self, scribe_agent):
        """Rescued defects have provenance fields set."""
        consolidated = []
        reviewer_outputs = [
            self._make_reviewer_output(
                [
                    self._make_defect(
                        "3.4.1", "Missing signal Ack",
                        defect_id="r1_1", reviewer_id="reviewer_1",
                        technique=ReadingTechnique.UBR,
                    ),
                ],
                reviewer_id="reviewer_1",
            ),
        ]

        result, count = scribe_agent._validate_and_rescue(consolidated, reviewer_outputs)

        assert count == 1
        assert result[0].source_defect_ids == ["r1_1"]
        assert result[0].source_reviewer_ids == ["reviewer_1"]
        assert result[0].source_techniques == ["UBR"]


class TestPositionDriftGuard:
    """Tests for position drift guard (TASK 2)."""

    @pytest.fixture
    def scribe_agent(self, tmp_path):
        """Create scribe agent with mock provider."""
        mock_provider = MagicMock()
        prompt_dir = tmp_path / "prompts"
        prompt_dir.mkdir()
        (prompt_dir / "scribe_meeting.txt").write_text("Test prompt")
        return ScribeAgent(mock_provider, prompt_dir)

    def test_allowed_position_accepts_valid(self, scribe_agent):
        """Defect with position in allowed set is accepted."""
        allowed = {"3.1", "3.2", "3.2.1", "3.3.1", "3.4.1", "3.4.2", "4.1", "4.2", "Table 1"}
        defect_data = {
            "position": "3.4.1",
            "page_hint": "p. 5",
            "description": "Missing signal",
            "evidence": "The diagram shows...",
            "risk": "A",
            "fault_type": "M",
        }
        result = scribe_agent._validate_defect_completeness(
            defect_data, allowed_position_tokens=allowed
        )
        assert result["is_complete"] is True

    def test_drift_guard_rejects_hallucinated(self, scribe_agent):
        """Defect with position NOT in allowed set is rejected."""
        allowed = {"3.1", "3.2", "3.2.1", "3.3.1", "3.4.1", "3.4.2", "4.1", "4.2", "Table 1"}
        defect_data = {
            "position": "3.5",
            "page_hint": "p. 6",
            "description": "Signal consistency issue",
            "evidence": "The definition does not match",
            "risk": "B",
            "fault_type": "W",
        }
        result = scribe_agent._validate_defect_completeness(
            defect_data, allowed_position_tokens=allowed
        )
        assert result["is_complete"] is False
        assert "hallucinated" in result["reason"].lower()

    def test_no_allowed_tokens_skips_guard(self, scribe_agent):
        """Without allowed tokens, drift guard is not applied."""
        defect_data = {
            "position": "3.5",
            "page_hint": "p. 6",
            "description": "Signal consistency issue",
            "evidence": "The definition does not match",
            "risk": "B",
            "fault_type": "W",
        }
        result = scribe_agent._validate_defect_completeness(
            defect_data, allowed_position_tokens=None
        )
        # Without allowed tokens, 3.5 passes basic validation (it's a valid 3.x token)
        assert result["is_complete"] is True

    def test_drift_guard_partial_hallucination(self, scribe_agent):
        """Defect with one valid and one hallucinated token is rejected."""
        allowed = {"3.1", "3.2", "3.4.1", "Table 1"}
        defect_data = {
            "position": "3.4.1, 3.5",
            "page_hint": "p. 6",
            "description": "Signal consistency issue",
            "evidence": "The definition does not match",
            "risk": "B",
            "fault_type": "W",
        }
        result = scribe_agent._validate_defect_completeness(
            defect_data, allowed_position_tokens=allowed
        )
        assert result["is_complete"] is False
        assert "3.5" in result["reason"]

    def test_drift_guard_autofix_single_mention(self, scribe_agent):
        """Hallucinated position is autofixed when exactly 1 valid mention in evidence."""
        allowed = {"3.1", "3.2", "3.4.1", "3.4.2", "4.1", "4.2", "Table 1"}
        defect_data = {
            "position": "3.5",
            "page_hint": "p. 7",
            "description": "Stop voice. The signal is missing.",
            "evidence": "Section 4.1 does not define the signal (p. 7)",
            "risk": "A",
            "fault_type": "M",
        }
        result = scribe_agent._validate_defect_completeness(
            defect_data, allowed_position_tokens=allowed
        )
        # Single mention (4.1) in evidence → autofix (soft canon: position stays original)
        assert result["is_complete"] is True
        assert defect_data["position"] == "3.5"  # soft canon: NOT overwritten
        assert defect_data.get("_canon_canonical") == "4.1"  # inferred stored here
        assert defect_data.get("_canon_autofixed") is True
        assert "position_autofixed" in defect_data.get("flags", [])

    def test_drift_guard_no_autofix_multiple_mentions(self, scribe_agent):
        """Hallucinated position NOT autofixed when multiple mentions exist."""
        allowed = {"3.1", "3.2", "3.4.1", "4.1", "4.2", "Table 1"}
        defect_data = {
            "position": "3.5",
            "page_hint": "p. 7",
            "description": "Signal defined in 4.1 and 4.2",
            "evidence": "See sections 4.1 and 4.2",
            "risk": "A",
            "fault_type": "M",
        }
        result = scribe_agent._validate_defect_completeness(
            defect_data, allowed_position_tokens=allowed
        )
        # Multiple mentions (4.1, 4.2) → no autofix → still rejected (hallucinated)
        assert result["is_complete"] is False

    def test_drift_guard_table_autofix(self, scribe_agent):
        """Table token autofixed when 'Table 1' is explicitly mentioned."""
        allowed = {"3.4.1", "3.4.2", "4.1", "Table 1"}
        defect_data = {
            "position": "3.5",
            "page_hint": "p. 5",
            "description": "Signal mismatch in Table 1",
            "evidence": "See Table 1 on page 5",
            "risk": "B",
            "fault_type": "W",
        }
        result = scribe_agent._validate_defect_completeness(
            defect_data, allowed_position_tokens=allowed
        )
        assert result["is_complete"] is True
        assert defect_data["position"] == "3.5"  # soft canon: NOT overwritten
        assert defect_data.get("_canon_canonical") == "Table 1"  # inferred stored here

    def test_canon_fields_stored_in_defect_data(self, scribe_agent):
        """Canonicalization results are stored in defect_data dict."""
        allowed = {"3.4.1", "3.4.2", "4.1", "Table 1"}
        defect_data = {
            "position": "3.4.1",
            "page_hint": "p. 7",
            "description": "Missing signal in 3.4.1",
            "evidence": "Section 3.4.1 shows...",
            "risk": "A",
            "fault_type": "M",
        }
        result = scribe_agent._validate_defect_completeness(
            defect_data, allowed_position_tokens=allowed
        )
        assert result["is_complete"] is True
        assert defect_data["_canon_canonical"] == "3.4.1"
        assert "_canon_mentions" in defect_data
        assert defect_data["_canon_drift_detected"] is False

    def test_position_mention_mismatch_autofixes(self, scribe_agent):
        """Valid position that disagrees with single text mention → autofix."""
        allowed = {"3.4.1", "3.4.2", "4.1", "4.2"}
        defect_data = {
            "position": "3.4.1",
            "page_hint": "p. 10",
            "description": "The signal is missing from 4.2",
            "evidence": "Section 4.2 lacks the signal",
            "risk": "A",
            "fault_type": "M",
        }
        result = scribe_agent._validate_defect_completeness(
            defect_data, allowed_position_tokens=allowed
        )
        assert result["is_complete"] is True
        assert defect_data["position"] == "3.4.1"  # soft canon: NOT overwritten
        assert defect_data.get("_canon_canonical") == "4.2"  # inferred stored here
        assert defect_data["_canon_autofixed"] is True


class TestConsolidateCanonFields:
    """Tests for position canonicalization fields on consolidated Defect objects."""

    @pytest.fixture
    def scribe_agent(self, tmp_path):
        """Create scribe agent with mock provider."""
        mock_provider = MagicMock()
        prompt_dir = tmp_path / "prompts"
        prompt_dir.mkdir()
        (prompt_dir / "scribe_meeting.txt").write_text("Test prompt")
        return ScribeAgent(mock_provider, prompt_dir)

    def test_consolidated_defect_has_canon_fields(self, scribe_agent):
        """Consolidated defects have position_canonical and position_mentions populated."""
        mock_response = """
        {
            "consolidated_defects": [
                {
                    "position": "Section 3.4.1",
                    "page_hint": "p. 7",
                    "description": "Missing signal in 3.4.1",
                    "evidence": "The diagram in 3.4.1 shows...",
                    "risk": "A",
                    "fault_type": "M",
                    "confidence": 0.9,
                    "flags": []
                }
            ],
            "duplicates_removed": 0,
            "conflicts_flagged": 0,
            "minutes": "Test meeting",
            "exit_decision": "Accept"
        }
        """
        scribe_agent.call_llm = MagicMock(return_value=mock_response)

        reviewer_output = ReviewerOutput(
            reviewer_id="test",
            technique=ReadingTechnique.UBR,
            defects=[],
            notes="",
        )

        allowed = {"3.4.1", "3.4.2", "4.1", "Table 1"}
        result = scribe_agent.consolidate([reviewer_output], allowed_position_tokens=allowed)

        defect = result.consolidated_defects[0]
        assert defect.position == "3.4.1"
        assert defect.position_canonical == "3.4.1"
        assert "3.4.1" in defect.position_mentions
        assert defect.position_autofixed is False

    def test_consolidated_defect_autofixed(self, scribe_agent):
        """Consolidated defect with drift gets autofixed and fields populated."""
        mock_response = """
        {
            "consolidated_defects": [
                {
                    "position": "3.5",
                    "page_hint": "p. 7",
                    "description": "Missing signal in MSC",
                    "evidence": "Section 4.1 does not define the signal (p. 7)",
                    "risk": "A",
                    "fault_type": "M",
                    "confidence": 0.9,
                    "flags": []
                }
            ],
            "duplicates_removed": 0,
            "conflicts_flagged": 0,
            "minutes": "Test meeting",
            "exit_decision": "Accept"
        }
        """
        scribe_agent.call_llm = MagicMock(return_value=mock_response)

        reviewer_output = ReviewerOutput(
            reviewer_id="test",
            technique=ReadingTechnique.UBR,
            defects=[],
            notes="",
        )

        allowed = {"3.4.1", "3.4.2", "4.1", "Table 1"}
        result = scribe_agent.consolidate([reviewer_output], allowed_position_tokens=allowed)

        defect = result.consolidated_defects[0]
        # Soft canon: position keeps the original reviewer value
        assert defect.position == "3.5"
        # Canonical stores the inferred position
        assert defect.position_canonical == "4.1"
        assert defect.position_autofixed is True
        assert defect.position_autofix_reason == "single_mentioned_token"
        assert defect.original_position == "3.5"
        assert "position_autofixed" in defect.flags
