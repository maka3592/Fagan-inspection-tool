"""Tests for DefectMatcher."""

import pytest
from fagan_tool.core.schemas import Defect, FaultType, GoldDefect, MatchType, RiskLevel
from fagan_tool.evaluation.matcher import DefectMatcher


@pytest.fixture
def matcher():
    """Create a matcher instance."""
    return DefectMatcher()


@pytest.fixture
def sample_gold_defects():
    """Create sample gold defects with valid position tokens (3.x, 4.x, Table)."""
    return [
        GoldDefect(
            id="G1",
            position="3.2",
            risk=RiskLevel.A,
            fault_type=FaultType.M,
            description="Missing error handling for null pointer",
            section="3.2",
            page="15",
        ),
        GoldDefect(
            id="G2",
            position="Table 1",
            risk=RiskLevel.B,
            fault_type=FaultType.W,
            description="Incorrect data type for user ID field",
            section="Table 1",
            page="20",
        ),
    ]


@pytest.fixture
def sample_found_defects():
    """Create sample found defects with valid position tokens."""
    return [
        Defect(
            id="F1",
            position="3.2",
            page_hint="p. 15",
            risk=RiskLevel.A,
            fault_type=FaultType.M,
            description="Missing null pointer error handling",
            evidence="Section 3.2 does not specify error handling (p. 15)",
            confidence=0.9,
        ),
        Defect(
            id="F2",
            position="Table 1",
            page_hint="p. 20",
            risk=RiskLevel.B,
            fault_type=FaultType.W,
            description="Wrong data type for user ID",
            evidence="Table 1 shows string instead of integer (p. 20)",
            confidence=0.85,
        ),
        Defect(
            id="F3",
            position="4.5",
            page_hint="p. 25",
            risk=RiskLevel.C,
            fault_type=FaultType.M,
            description="Missing validation for input field",
            evidence="Section 4.5 does not mention validation (p. 25)",
            confidence=0.7,
        ),
    ]


def test_exact_match(matcher, sample_gold_defects, sample_found_defects):
    """Test exact matching between found and gold defects."""
    matches, stats = matcher.match([sample_found_defects[0]], [sample_gold_defects[0]])

    assert len(matches) == 1
    assert matches[0].match_type in [MatchType.EXACT, MatchType.PARTIAL]
    assert matches[0].gold_id == "G1"
    assert matches[0].similarity_score > 0.7


def test_no_match_potential_new(matcher, sample_gold_defects):
    """Test defect with no match classified as potential new."""
    # Use valid position token (4.9) but one not in gold
    found_defect = Defect(
        id="F_NEW",
        position="4.9",
        risk=RiskLevel.B,
        fault_type=FaultType.M,
        description="New defect not in gold",
        evidence="Section 4.9 missing (p. 50)",
        confidence=0.8,
    )

    matches, stats = matcher.match([found_defect], sample_gold_defects)

    assert len(matches) == 1
    assert matches[0].match_type == MatchType.NO_MATCH_POTENTIAL_NEW
    assert matches[0].gold_id is None


def test_no_match_false_positive(matcher, sample_gold_defects):
    """Test low-confidence defect with no match classified as false positive."""
    # Use valid position token but one not in gold
    found_defect = Defect(
        id="F_FP",
        position="4.8",
        risk=RiskLevel.C,
        fault_type=FaultType.M,
        description="Questionable defect",
        evidence="Weak evidence",
        confidence=0.4,
    )

    matches, stats = matcher.match([found_defect], sample_gold_defects)

    assert len(matches) == 1
    assert matches[0].match_type == MatchType.NO_MATCH_FALSE_POSITIVE


def test_duplicate_detection(matcher):
    """Test duplicate defect detection - requires shared position token."""
    found_defects = [
        Defect(
            id="F1",
            position="3.1",
            risk=RiskLevel.A,
            fault_type=FaultType.M,
            description="Missing error handling",
            evidence="Section 3.1 (p. 10)",
            confidence=0.9,
        ),
        Defect(
            id="F2",
            position="3.1",
            risk=RiskLevel.A,
            fault_type=FaultType.M,
            description="Missing error handling code",
            evidence="Section 3.1 (p. 10)",
            confidence=0.85,
        ),
    ]

    gold_defects = [
        GoldDefect(
            id="G1",
            position="3.1",
            risk=RiskLevel.A,
            fault_type=FaultType.M,
            description="Missing error handling",
        )
    ]

    matches, stats = matcher.match(found_defects, gold_defects)

    # Should have one match to gold and one duplicate
    match_types = [m.match_type for m in matches]
    assert MatchType.DUPLICATE in match_types or len([m for m in matches if m.gold_id == "G1"]) == 1


def test_stats_calculation(matcher, sample_gold_defects, sample_found_defects):
    """Test that match statistics are calculated correctly."""
    matches, stats = matcher.match(sample_found_defects, sample_gold_defects)

    assert "total_found" in stats
    assert "total_gold" in stats
    assert "matched" in stats
    assert stats["total_found"] == len(sample_found_defects)
    assert stats["total_gold"] == len(sample_gold_defects)


def test_normalize_position(matcher):
    """Test position normalization."""
    pos1 = matcher._normalize_position("Section 3.2")
    pos2 = matcher._normalize_position("section 3.2")
    pos3 = matcher._normalize_position("Page 15, Section 3.2")

    assert pos1 == pos2
    assert "section" not in pos1.lower()


def test_is_out_of_scope_use_case(matcher):
    """Test that Use Case defects are classified as out-of-scope."""
    use_case_defect = Defect(
        id="F_UC",
        position="Use Case 2.1",
        risk=RiskLevel.B,
        fault_type=FaultType.M,
        description="Missing precondition",
        evidence="Use case lacks precondition",
        confidence=0.8,
    )

    assert matcher._is_out_of_scope(use_case_defect) is True


def test_is_in_scope_design_section(matcher):
    """Test that Design section defects are classified as in-scope."""
    design_defect = Defect(
        id="F_DES",
        position="Section 4.1",
        risk=RiskLevel.A,
        fault_type=FaultType.M,
        description="Missing signal definition",
        evidence="Section 4.1 missing signal",
        confidence=0.9,
    )

    assert matcher._is_out_of_scope(design_defect) is False


def test_is_in_scope_msc_section(matcher):
    """Test that MSC defects are classified as in-scope."""
    msc_defect = Defect(
        id="F_MSC",
        position="Section 3.2.1",
        risk=RiskLevel.B,
        fault_type=FaultType.W,
        description="Wrong message sequence",
        evidence="MSC shows incorrect order",
        confidence=0.85,
    )

    assert matcher._is_out_of_scope(msc_defect) is False


def test_out_of_scope_fp_notes(matcher, sample_gold_defects):
    """Test that out-of-scope defects get appropriate notes."""
    use_case_defect = Defect(
        id="F_UC",
        position="Use Case 2.3",
        risk=RiskLevel.C,
        fault_type=FaultType.M,
        description="Missing use case step",
        evidence="Use case incomplete",
        confidence=0.75,
    )

    matches, _ = matcher.match([use_case_defect], sample_gold_defects)

    assert len(matches) == 1
    assert matches[0].match_type == MatchType.NO_MATCH_POTENTIAL_NEW
    assert "(out-of-scope: use case)" in matches[0].notes


def test_in_scope_fp_notes(matcher, sample_gold_defects):
    """Test that in-scope defects get appropriate notes."""
    design_defect = Defect(
        id="F_DES",
        position="4.5",
        risk=RiskLevel.B,
        fault_type=FaultType.M,
        description="Missing interface definition",
        evidence="Section 4.5 incomplete",
        confidence=0.8,
    )

    matches, _ = matcher.match([design_defect], sample_gold_defects)

    assert len(matches) == 1
    assert matches[0].match_type == MatchType.NO_MATCH_POTENTIAL_NEW
    assert "(in-scope)" in matches[0].notes
    assert "out-of-scope" not in matches[0].notes


class TestPositionTokenFiltering:
    """Tests for position token-based candidate filtering."""

    def test_different_sections_no_match(self, matcher):
        """Regression: Different sections (3.1 vs 3.2.1) must NOT match."""
        found = Defect(
            id="F1",
            position="3.1",
            risk=RiskLevel.A,
            fault_type=FaultType.M,
            description="Address field is incorrectly defined as integer",
            evidence="Section 3.1 shows wrong type",
            confidence=0.9,
        )
        gold = [
            GoldDefect(
                id="G1",
                position="3.2.1",
                risk=RiskLevel.A,
                fault_type=FaultType.M,
                description="Reset Alarm signal is missing",
            )
        ]

        matches, stats = matcher.match([found], gold)

        # Should NOT match - different sections
        assert matches[0].match_type in [MatchType.NO_MATCH_POTENTIAL_NEW, MatchType.NO_MATCH_FALSE_POSITIVE]
        assert matches[0].gold_id is None

    def test_shared_token_matches(self, matcher):
        """Defects with shared position token and signal token can match."""
        found = Defect(
            id="F1",
            position="3.4.1",
            risk=RiskLevel.B,
            fault_type=FaultType.M,
            description="Cancel_Order signal is missing from design",
            evidence="Section 3.4.1 does not define 'Cancel_Order' signal.",
            confidence=0.85,
        )
        gold = [
            GoldDefect(
                id="G1",
                position="3.2.1, 3.4.1, 3.4.2",
                risk=RiskLevel.B,
                fault_type=FaultType.M,
                description="Cancel_Order signal is missing in the design",
            )
        ]

        matches, stats = matcher.match([found], gold)

        # Should match - shares 3.4.1 position AND Cancel_Order signal
        assert matches[0].match_type in [MatchType.EXACT, MatchType.PARTIAL]
        assert matches[0].gold_id == "G1"

    def test_table_token_matches(self, matcher):
        """Table references with shared signal can match."""
        found = Defect(
            id="F1",
            position="Table 1, 3.4.2",
            risk=RiskLevel.B,
            fault_type=FaultType.M,
            description="Cancel_Order signal missing from Table 1",
            evidence="Table 1 does not list 'Cancel_Order'.",
            confidence=0.8,
        )
        gold = [
            GoldDefect(
                id="G1",
                position="3.2.1, 3.4.2, Table 1",
                risk=RiskLevel.B,
                fault_type=FaultType.M,
                description="Cancel_Order signal missing in Table 1",
            )
        ]

        matches, stats = matcher.match([found], gold)

        # Should match - shares Table 1, 3.4.2 position AND Cancel_Order signal
        assert matches[0].match_type in [MatchType.EXACT, MatchType.PARTIAL]
        assert matches[0].gold_id == "G1"

    def test_adjacent_sections_no_match(self, matcher):
        """Adjacent sections (4.1 vs 4.2) must NOT match."""
        found = Defect(
            id="F1",
            position="4.1",
            risk=RiskLevel.B,
            fault_type=FaultType.M,
            description="Signal ordering issue",
            evidence="Section 4.1 shows wrong order",
            confidence=0.85,
        )
        gold = [
            GoldDefect(
                id="G1",
                position="4.2",
                risk=RiskLevel.B,
                fault_type=FaultType.M,
                description="Signal ordering issue in diagram",
            )
        ]

        matches, stats = matcher.match([found], gold)

        # Should NOT match - 4.1 != 4.2
        assert matches[0].match_type in [MatchType.NO_MATCH_POTENTIAL_NEW, MatchType.NO_MATCH_FALSE_POSITIVE]
        assert matches[0].gold_id is None

    def test_no_token_no_match(self, matcher):
        """Defects without valid position tokens don't match gold."""
        found = Defect(
            id="F1",
            position="Overview",
            risk=RiskLevel.C,
            fault_type=FaultType.M,
            description="Overview incomplete",
            evidence="Overview section",
            confidence=0.7,
        )
        gold = [
            GoldDefect(
                id="G1",
                position="3.1",
                risk=RiskLevel.C,
                fault_type=FaultType.M,
                description="Overview incomplete",
            )
        ]

        matches, stats = matcher.match([found], gold)

        # Should NOT match - no valid token in found
        assert matches[0].match_type in [MatchType.NO_MATCH_POTENTIAL_NEW, MatchType.NO_MATCH_FALSE_POSITIVE]


class TestSignalTokenFiltering:
    """Tests for signal token-based match constraint."""

    def test_reject_order_vs_start_alarm_no_match(self, matcher):
        """Regression: Reject_Order ack vs Start alarm must NOT match despite same position."""
        found = Defect(
            id="F1",
            position="3.2.1",
            risk=RiskLevel.A,
            fault_type=FaultType.M,
            description="Reject Orders. The signal 'Reject_Order' is missing an acknowledgment signal.",
            evidence="The signal 'Reject_Order' is sent when the driver rejects (p. 3).",
            confidence=0.9,
        )
        gold = [
            GoldDefect(
                id="G23",
                position="3.2.1",
                risk=RiskLevel.A,
                fault_type=FaultType.M,
                description='Start alarm is missing. The signal "start alarm" is missiing.',
            )
        ]

        matches, stats = matcher.match([found], gold)

        # Different signals at same position - must NOT match
        assert matches[0].match_type in [MatchType.NO_MATCH_POTENTIAL_NEW, MatchType.NO_MATCH_FALSE_POSITIVE]
        assert matches[0].gold_id is None

    def test_order_vs_logged_in_no_match(self, matcher):
        """Regression: Order params vs Logged In params must NOT match."""
        found = Defect(
            id="F1",
            position="Table 1",
            risk=RiskLevel.B,
            fault_type=FaultType.W,
            description="Order parameters. The signal 'Order' has wrong parameter types in Table 1.",
            evidence="Table 1 indicates 'Order' should have additional parameters.",
            confidence=0.8,
        )
        gold = [
            GoldDefect(
                id="G27",
                position="Table 1, 3.4.2",
                risk=RiskLevel.B,
                fault_type=FaultType.W,
                description='Logged in parameters. The signal "Logged In" misses parameters.',
            )
        ]

        matches, stats = matcher.match([found], gold)

        # Different signals - must NOT match
        assert matches[0].match_type in [MatchType.NO_MATCH_POTENTIAL_NEW, MatchType.NO_MATCH_FALSE_POSITIVE]
        assert matches[0].gold_id is None

    def test_no_signals_low_similarity_no_match(self, matcher):
        """No signal tokens + low description similarity → must NOT match (GATE 3)."""
        found = Defect(
            id="F1",
            position="3.4.1",
            risk=RiskLevel.A,
            fault_type=FaultType.M,
            description="Reject Orders. A signal is missing for not confirming orders.",
            evidence="The MSC in 4.1 does not include a reject signal.",
            confidence=0.85,
        )
        gold = [
            GoldDefect(
                id="G14",
                position="3.2.2, 3.3.1, 3.4.1, 4.1, Table 1",
                risk=RiskLevel.A,
                fault_type=FaultType.M,
                description="Confirm Order. A taxi driver/operator cannot confirm an order.",
            )
        ]

        matches, stats = matcher.match([found], gold)

        # Neither side has explicit signal tokens AND description similarity < 0.80
        # → GATE 3 blocks the match
        assert matches[0].match_type in [MatchType.NO_MATCH_POTENTIAL_NEW, MatchType.NO_MATCH_FALSE_POSITIVE]
        assert matches[0].gold_id is None

    def test_shared_signal_token_matches(self, matcher):
        """Defects with same signal token should match normally."""
        found = Defect(
            id="F1",
            position="3.3.1",
            risk=RiskLevel.B,
            fault_type=FaultType.W,
            description="Allocate_car parameters. The signal 'Allocate_car' has incorrect parameter types.",
            evidence="The first parameter should be a string.",
            confidence=0.75,
        )
        gold = [
            GoldDefect(
                id="G7",
                position="3.3.1, 3.3.2",
                risk=RiskLevel.B,
                fault_type=FaultType.W,
                description="Allocate car. Requirement 3.2.4 and the design of allocate_car do not correspond.",
            )
        ]

        matches, stats = matcher.match([found], gold)

        # Both mention allocate_car - should match
        assert matches[0].match_type in [MatchType.EXACT, MatchType.PARTIAL]
        assert matches[0].gold_id == "G7"

    def test_signal_extracted_from_evidence(self, matcher):
        """Signal token in evidence (not description) should still gate correctly."""
        found = Defect(
            id="F1",
            position="3.2.1",
            risk=RiskLevel.A,
            fault_type=FaultType.M,
            description="Missing acknowledgment signal for order rejection.",
            evidence="The signal 'Reject_Order' is sent but has no ack (p. 3).",
            confidence=0.9,
        )
        gold = [
            GoldDefect(
                id="G23",
                position="3.2.1",
                risk=RiskLevel.A,
                fault_type=FaultType.M,
                description='Start alarm is missing. The signal "start alarm" is missiing.',
            )
        ]

        matches, stats = matcher.match([found], gold)

        # Found has 'Reject_Order' in evidence, gold has 'start_alarm'
        # Both have signals but they don't overlap → GATE 2 blocks
        assert matches[0].match_type in [MatchType.NO_MATCH_POTENTIAL_NEW, MatchType.NO_MATCH_FALSE_POSITIVE]
        assert matches[0].gold_id is None

    def test_signal_in_evidence_enables_match(self, matcher):
        """Signal token found via evidence enables matching when description lacks explicit signal form."""
        found = Defect(
            id="F1",
            position="3.3.1",
            risk=RiskLevel.B,
            fault_type=FaultType.W,
            description="Allocate car design does not correspond to requirement.",
            evidence="The signal 'Allocate_car' has incorrect parameter types (p. 8).",
            confidence=0.75,
        )
        gold = [
            GoldDefect(
                id="G7",
                position="3.3.1, 3.3.2",
                risk=RiskLevel.B,
                fault_type=FaultType.W,
                description="Allocate car. Requirement 3.2.4 and the design of allocate_car do not correspond.",
            )
        ]

        matches, stats = matcher.match([found], gold)

        # Found has 'allocate_car' in evidence, gold has 'allocate_car' in description
        # Signal overlap confirmed → match proceeds normally
        assert matches[0].match_type in [MatchType.EXACT, MatchType.PARTIAL]
        assert matches[0].gold_id == "G7"

    def test_no_signal_high_similarity_still_matches(self, matcher):
        """No signal tokens but very high description similarity (>= 0.80) passes GATE 3."""
        found = Defect(
            id="F1",
            position="3.2",
            risk=RiskLevel.A,
            fault_type=FaultType.M,
            description="Missing error handling for null pointer exception",
            evidence="Section 3.2 does not specify error handling (p. 15)",
            confidence=0.9,
        )
        gold = [
            GoldDefect(
                id="G1",
                position="3.2",
                risk=RiskLevel.A,
                fault_type=FaultType.M,
                description="Missing error handling for null pointer",
            )
        ]

        matches, stats = matcher.match([found], gold)

        # Neither side has signal tokens but descriptions are very similar (>= 0.80)
        # → passes GATE 3 and matches
        assert matches[0].match_type in [MatchType.EXACT, MatchType.PARTIAL]
        assert matches[0].gold_id == "G1"

    def test_no_signal_moderate_similarity_no_match(self, matcher):
        """No signal tokens + moderate similarity (< 0.80) → GATE 3 blocks."""
        found = Defect(
            id="F1",
            position="Table 1",
            risk=RiskLevel.B,
            fault_type=FaultType.W,
            description="Parameter type mismatch in data table definition",
            evidence="Table 1 shows inconsistent types",
            confidence=0.8,
        )
        gold = [
            GoldDefect(
                id="G2",
                position="Table 1",
                risk=RiskLevel.B,
                fault_type=FaultType.W,
                description="Incorrect data type for user ID field",
            )
        ]

        matches, stats = matcher.match([found], gold)

        # Same position but no signal tokens and description similarity < 0.80
        # → GATE 3 blocks the match
        assert matches[0].match_type in [MatchType.NO_MATCH_POTENTIAL_NEW, MatchType.NO_MATCH_FALSE_POSITIVE]
        assert matches[0].gold_id is None


class TestDebugFields:
    """Tests for debug fields on DefectMatch."""

    def test_no_match_has_best_candidate(self, matcher):
        """Unmatched defect should have best_candidate populated."""
        found = Defect(
            id="F1",
            position="3.2.1",
            risk=RiskLevel.A,
            fault_type=FaultType.M,
            description="Reject Orders. The signal 'Reject_Order' is missing an ack.",
            evidence="The signal 'Reject_Order' is sent when the driver rejects (p. 3).",
            confidence=0.9,
        )
        gold = [
            GoldDefect(
                id="G23",
                position="3.2.1",
                risk=RiskLevel.A,
                fault_type=FaultType.M,
                description='Start alarm is missing. The signal "start alarm" is missiing.',
            )
        ]

        matches, _ = matcher.match([found], gold)

        assert len(matches) == 1
        assert matches[0].gold_id is None  # no match
        assert matches[0].best_candidate_gold_id == "G23"
        assert matches[0].best_candidate_gold_position == "3.2.1"
        assert matches[0].best_candidate_match_reason == "no_signal_overlap"

    def test_matched_defect_has_debug_fields(self, matcher):
        """Matched defect should have reason='matched' and candidate info."""
        found = Defect(
            id="F1",
            position="3.2",
            risk=RiskLevel.A,
            fault_type=FaultType.M,
            description="Missing error handling for null pointer exception",
            evidence="Section 3.2 does not specify error handling (p. 15)",
            confidence=0.9,
        )
        gold = [
            GoldDefect(
                id="G1",
                position="3.2",
                risk=RiskLevel.A,
                fault_type=FaultType.M,
                description="Missing error handling for null pointer",
            )
        ]

        matches, _ = matcher.match([found], gold)

        assert len(matches) == 1
        assert matches[0].gold_id == "G1"
        assert matches[0].best_candidate_match_reason == "matched"
        assert matches[0].best_candidate_gold_id == "G1"
        assert matches[0].best_candidate_similarity > 0.0

    def test_no_gold_candidates_reason(self, matcher):
        """Empty gold list should give reason='no_candidates'."""
        found = Defect(
            id="F1",
            position="3.1",
            risk=RiskLevel.B,
            fault_type=FaultType.M,
            description="Missing signal definition",
            evidence="Section 3.1",
            confidence=0.8,
        )

        matches, _ = matcher.match([found], [])

        assert len(matches) == 1
        assert matches[0].best_candidate_match_reason == "no_candidates"
        assert matches[0].best_candidate_gold_id is None

    def test_gate1_blocked_reason(self, matcher):
        """Position mismatch should give reason='no_position_overlap'."""
        found = Defect(
            id="F1",
            position="3.1",
            risk=RiskLevel.A,
            fault_type=FaultType.M,
            description="Missing signal definition",
            evidence="Section 3.1",
            confidence=0.9,
        )
        gold = [
            GoldDefect(
                id="G1",
                position="4.2",
                risk=RiskLevel.A,
                fault_type=FaultType.M,
                description="Missing signal definition",
            )
        ]

        matches, _ = matcher.match([found], gold)

        assert len(matches) == 1
        assert matches[0].gold_id is None
        assert matches[0].best_candidate_match_reason == "no_position_overlap"
        assert matches[0].best_candidate_gold_id == "G1"


class TestUnionPositionMatching:
    """Regression tests for union position matching (TP=0 fix).

    When soft canonicalization is active, defect.position keeps the
    reviewer-original value and position_canonical stores the inferred
    section.  The matcher must use the UNION of tokens from position,
    original_position, and position_canonical so that matches succeed
    on either the original or the inferred section.
    """

    def test_match_via_original_position(self, matcher):
        """Found position matches gold — should match even with different canonical."""
        found = Defect(
            id="F1",
            position="3.2.1",
            risk=RiskLevel.A,
            fault_type=FaultType.M,
            description="Reject Orders. The signal 'Reject_Order' is missing an ack.",
            evidence="The signal 'Reject_Order' is sent but has no ack (p. 3).",
            confidence=0.9,
            original_position=None,
            position_canonical="4.1",  # different from gold, but position matches
        )
        gold = [
            GoldDefect(
                id="G1",
                position="3.2.1",
                risk=RiskLevel.A,
                fault_type=FaultType.M,
                description="Reject Orders. The signal 'Reject_Order' needs acknowledgment.",
            )
        ]

        matches, _ = matcher.match([found], gold)

        # Should match via position "3.2.1" (union includes it)
        assert matches[0].match_type in [MatchType.EXACT, MatchType.PARTIAL]
        assert matches[0].gold_id == "G1"

    def test_match_via_canonical_position(self, matcher):
        """Gold position matches canonical — should match even though position differs."""
        found = Defect(
            id="F1",
            position="3.2.1",  # does NOT overlap with gold "4.1"
            risk=RiskLevel.A,
            fault_type=FaultType.M,
            description="Reject Orders. The signal 'Reject_Order' is missing an ack.",
            evidence="The signal 'Reject_Order' is sent but has no ack (p. 3).",
            confidence=0.9,
            original_position=None,
            position_canonical="4.1",  # matches gold
        )
        gold = [
            GoldDefect(
                id="G1",
                position="4.1",
                risk=RiskLevel.A,
                fault_type=FaultType.M,
                description="Reject Orders. The signal 'Reject_Order' needs acknowledgment.",
            )
        ]

        matches, _ = matcher.match([found], gold)

        # Should match via position_canonical "4.1" (union includes it)
        assert matches[0].match_type in [MatchType.EXACT, MatchType.PARTIAL]
        assert matches[0].gold_id == "G1"

    def test_legacy_defect_without_new_fields(self, matcher):
        """Old defects without original_position/position_canonical work identically."""
        found = Defect(
            id="F1",
            position="3.4.1",
            risk=RiskLevel.B,
            fault_type=FaultType.M,
            description="Cancel_Order signal is missing from design",
            evidence="Section 3.4.1 does not define 'Cancel_Order' signal.",
            confidence=0.85,
            # No original_position or position_canonical set (defaults to None)
        )
        gold = [
            GoldDefect(
                id="G1",
                position="3.2.1, 3.4.1, 3.4.2",
                risk=RiskLevel.B,
                fault_type=FaultType.M,
                description="Cancel_Order signal is missing in the design",
            )
        ]

        matches, _ = matcher.match([found], gold)

        # Should still match via position "3.4.1" — backward compatible
        assert matches[0].match_type in [MatchType.EXACT, MatchType.PARTIAL]
        assert matches[0].gold_id == "G1"

    def test_no_overlap_even_with_canonical(self, matcher):
        """When neither position nor canonical overlap gold, still no match."""
        found = Defect(
            id="F1",
            position="3.1",
            risk=RiskLevel.A,
            fault_type=FaultType.M,
            description="Missing signal definition",
            evidence="Section 3.1",
            confidence=0.9,
            original_position=None,
            position_canonical="3.3",
        )
        gold = [
            GoldDefect(
                id="G1",
                position="4.2",
                risk=RiskLevel.A,
                fault_type=FaultType.M,
                description="Missing signal definition",
            )
        ]

        matches, _ = matcher.match([found], gold)

        # Union {3.1, 3.3} has no overlap with {4.2}
        assert matches[0].gold_id is None
        assert matches[0].match_type in [
            MatchType.NO_MATCH_POTENTIAL_NEW,
            MatchType.NO_MATCH_FALSE_POSITIVE,
        ]


class TestTopicPrefixRegression:
    """Regression tests for topic prefix signal extraction in matching."""

    def test_reject_order_topic_no_match_start_alarm(self, matcher):
        """Different topic prefixes at same position must not match."""
        found = Defect(
            id="F1",
            position="3.2.1",
            risk=RiskLevel.A,
            fault_type=FaultType.M,
            description="Reject Orders. A signal is missing for not confirming orders.",
            evidence="The MSC in 3.2.1 does not include a reject signal.",
            confidence=0.9,
        )
        gold = [
            GoldDefect(
                id="G23",
                position="3.2.1",
                risk=RiskLevel.A,
                fault_type=FaultType.M,
                description="Start alarm. The signal 'start alarm' is missing.",
            )
        ]

        matches, _ = matcher.match([found], gold)

        # Topic prefixes differ (reject_orders vs start_alarm) → GATE 2 blocks
        assert matches[0].match_type in [MatchType.NO_MATCH_POTENTIAL_NEW, MatchType.NO_MATCH_FALSE_POSITIVE]
        assert matches[0].gold_id is None


class TestOverlapCoefficientScoring:
    """Tests for overlap coefficient position scoring."""

    def test_superset_tokens_score_1(self, matcher):
        """Found with superset of gold tokens → position score = 1.0 (not penalised)."""
        found = Defect(
            id="F1",
            position="3.2.1, 3.4.1, 3.4.2, Table 1",
            risk=RiskLevel.A,
            fault_type=FaultType.M,
            description="Cancel order. The signal 'Cancel_Order' is missing.",
            evidence="Table 1 does not list 'Cancel_Order'.",
            confidence=0.9,
        )
        gold = [
            GoldDefect(
                id="G1",
                position="3.4.2",
                risk=RiskLevel.A,
                fault_type=FaultType.M,
                description="Cancel order. The signal 'Cancel_Order' is missing.",
            )
        ]

        matches, _ = matcher.match([found], gold)

        # Found tokens {3.2.1, 3.4.1, 3.4.2, Table 1} ⊇ gold {3.4.2}
        # Overlap coefficient = 1/1 = 1.0 → max position credit
        assert matches[0].match_type in [MatchType.EXACT, MatchType.PARTIAL]
        assert matches[0].gold_id == "G1"
        # Score should be higher than old fixed 0.9 * 0.3 = 0.27 position credit
        assert matches[0].similarity_score > 0.85

    def test_exact_tokens_score_1(self, matcher):
        """Identical token sets → position score = 1.0."""
        found = Defect(
            id="F1",
            position="3.3.1, 3.3.2",
            risk=RiskLevel.B,
            fault_type=FaultType.W,
            description="Allocate car. The design of allocate_car does not correspond.",
            evidence="Section 3.3.1 shows wrong params.",
            confidence=0.85,
        )
        gold = [
            GoldDefect(
                id="G1",
                position="3.3.1, 3.3.2",
                risk=RiskLevel.B,
                fault_type=FaultType.W,
                description="Allocate car. Requirement 3.2.4 and the design of allocate_car do not correspond.",
            )
        ]

        matches, _ = matcher.match([found], gold)

        assert matches[0].match_type in [MatchType.EXACT, MatchType.PARTIAL]
        assert matches[0].gold_id == "G1"

    def test_partial_overlap_proportional(self, matcher):
        """Partial overlap → position score proportional to overlap coefficient."""
        from fagan_tool.evaluation.matcher import SimilarityResult

        # found has {3.2.1, 3.4.1}, gold has {3.4.1, 3.4.2}
        # intersection = {3.4.1}, min_size = 2
        # overlap coefficient = 1/2 = 0.5
        found = Defect(
            id="F1",
            position="3.2.1, 3.4.1",
            risk=RiskLevel.A,
            fault_type=FaultType.M,
            description="Cancel order. The signal 'Cancel_Order' is missing.",
            evidence="The design is missing 'Cancel_Order'.",
            confidence=0.9,
        )
        gold = GoldDefect(
            id="G1",
            position="3.4.1, 3.4.2",
            risk=RiskLevel.A,
            fault_type=FaultType.M,
            description="Cancel order. The signal 'Cancel_Order' is missing in the design.",
        )

        result = matcher._calculate_similarity(found, gold)

        # Should pass gates and have score reflecting 0.5 position overlap
        assert result.reason == "matched"
        # pos_sim = 0.5 → pos_component = 0.5 * 0.3 = 0.15
        # (vs old fixed 0.9 * 0.3 = 0.27)
        assert result.score > 0.0


class TestGate3RelaxedForOneSignalSide:
    """Tests that GATE 3 only blocks when NEITHER side has signals."""

    def test_found_has_signals_gold_does_not(self, matcher):
        """Found has signals, gold doesn't → GATE 3 should NOT block.

        This reproduces the TP=0 failure: found defects have signal-first
        format ('Signal_Name': ...) but gold descriptions are generic.
        Combined score threshold is the only gatekeeper.
        """
        found = Defect(
            id="F1",
            position="3.4.2",
            risk=RiskLevel.A,
            fault_type=FaultType.M,
            description="'Cancel_Order': The signal is missing from Table 1.",
            evidence="The signal 'Cancel_Order' is not defined in Table 1.",
            confidence=0.9,
        )
        gold = [
            GoldDefect(
                id="G1",
                position="3.4.2",
                risk=RiskLevel.A,
                fault_type=FaultType.M,
                # Generic description without identifiable signal tokens
                description="A signal is missing from the design. The order cancellation is not implemented.",
            )
        ]

        matches, _ = matcher.match([found], gold)

        # OLD behaviour: GATE 3 blocks (gold has no signals, desc_sim < 0.80)
        # → match_type would be no_match
        #
        # NEW behaviour: GATE 3 only blocks when NEITHER side has signals.
        # Found has 'cancel_order' signal, so GATE 3 doesn't apply.
        # Combined score decides (should match if desc_sim is reasonable).
        assert matches[0].gold_id == "G1"
        assert matches[0].match_type in [MatchType.EXACT, MatchType.PARTIAL]

    def test_neither_has_signals_still_blocked(self, matcher):
        """Neither side has signals + low desc_sim → GATE 3 still blocks."""
        found = Defect(
            id="F1",
            position="3.4.1",
            risk=RiskLevel.A,
            fault_type=FaultType.M,
            description="A signal is missing for not confirming orders.",
            evidence="The MSC does not include a signal.",
            confidence=0.85,
        )
        gold = [
            GoldDefect(
                id="G1",
                position="3.4.1",
                risk=RiskLevel.A,
                fault_type=FaultType.M,
                description="A timeout is not specified for voice communication.",
            )
        ]

        matches, _ = matcher.match([found], gold)

        # Neither side has signals, descriptions are quite different
        # → GATE 3 should still block (desc_sim < 0.80)
        assert matches[0].gold_id is None
        assert matches[0].match_type in [
            MatchType.NO_MATCH_POTENTIAL_NEW,
            MatchType.NO_MATCH_FALSE_POSITIVE,
        ]

    def test_tp0_regression_found_signal_format(self, matcher):
        """Regression: signal-first found defect matching generic gold must produce TP > 0.

        This test reproduces the exact failure mode from thesis_unionpos run:
        Found defects use 'Signal_Name': format, gold defects are generic.
        """
        found_defects = [
            Defect(
                id="F1",
                position="3.3.1",
                risk=RiskLevel.B,
                fault_type=FaultType.W,
                description="'Allocate_car': The signal is missing from Table 1.",
                evidence="The signal 'Allocate_car' is referenced in section 3.3.1.",
                confidence=0.9,
            ),
            Defect(
                id="F2",
                position="3.2.1",
                risk=RiskLevel.A,
                fault_type=FaultType.M,
                description="'Start_Voice': The signal is missing from the design.",
                evidence="The signal 'Start_Voice' is not defined in section 3.2.1.",
                confidence=0.85,
            ),
        ]
        gold_defects = [
            GoldDefect(
                id="G7",
                position="3.3.1, 3.3.2",
                risk=RiskLevel.B,
                fault_type=FaultType.W,
                description="Allocate car. Requirement 3.2.4 and the design of allocate_car do not correspond.",
            ),
            GoldDefect(
                id="G23",
                position="3.2.1",
                risk=RiskLevel.A,
                fault_type=FaultType.M,
                description='Start alarm is missing. The signal "start alarm" is missiing.',
            ),
        ]

        matches, stats = matcher.match(found_defects, gold_defects)

        # Must produce at least 1 TP (F1↔G7 share allocate_car signal + position)
        tp_matches = [m for m in matches if m.gold_id is not None]
        assert len(tp_matches) >= 1, (
            f"Expected ≥1 TP but got {len(tp_matches)}. "
            f"Reasons: {[(m.found_id, m.best_candidate_match_reason) for m in matches]}"
        )
        assert stats["matched"] >= 1
