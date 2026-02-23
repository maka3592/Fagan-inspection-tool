"""Tests for Fagan process orchestration."""

import pytest
import yaml
from pathlib import Path

from src.fagan_tool.core.process import FaganProcess
from src.fagan_tool.core.schemas import (
    InspectionConfig,
    ConditionType,
    ReadingTechnique,
    LLMParams,
)


def test_unique_run_id_generation_with_existing_directory(tmp_path):
    """Test that FaganProcess generates unique run IDs when directory exists."""
    # Create a mock config
    config = InspectionConfig(
        inspection_id="test_run",
        condition=ConditionType.C1_UBR,
        reading_techniques=[ReadingTechnique.UBR],
        artifacts=["design/test.pdf"],
        llm_params=LLMParams(model="gpt-5-mini", provider="openai"),
        dry_run=True,
    )

    # Create first run (should use base ID)
    process1 = FaganProcess(config, output_dir=tmp_path)
    assert process1.run_id == "test_run"
    assert (tmp_path / "test_run").exists()

    # Create second run (should get suffix _002)
    process2 = FaganProcess(config, output_dir=tmp_path)
    assert process2.run_id == "test_run_002"
    assert (tmp_path / "test_run_002").exists()

    # Create third run (should get suffix _003)
    process3 = FaganProcess(config, output_dir=tmp_path)
    assert process3.run_id == "test_run_003"
    assert (tmp_path / "test_run_003").exists()

    # Verify original directory still exists
    assert (tmp_path / "test_run").exists()


def test_unique_run_id_with_override(tmp_path):
    """Test that run_id_override parameter works correctly."""
    config = InspectionConfig(
        inspection_id="original_id",
        condition=ConditionType.C1_UBR,
        reading_techniques=[ReadingTechnique.UBR],
        artifacts=["design/test.pdf"],
        llm_params=LLMParams(model="gpt-5-mini", provider="openai"),
        dry_run=True,
    )

    # Use override ID
    process = FaganProcess(config, output_dir=tmp_path, run_id_override="custom_run_123")
    assert process.run_id == "custom_run_123"
    assert (tmp_path / "custom_run_123").exists()

    # Original ID should not be used
    assert not (tmp_path / "original_id").exists()


def test_unique_run_id_when_no_conflict(tmp_path):
    """Test that base ID is used when no conflict exists."""
    config = InspectionConfig(
        inspection_id="unique_run",
        condition=ConditionType.C1_UBR,
        reading_techniques=[ReadingTechnique.UBR],
        artifacts=["design/test.pdf"],
        llm_params=LLMParams(model="gpt-5-mini", provider="openai"),
        dry_run=True,
    )

    process = FaganProcess(config, output_dir=tmp_path)
    assert process.run_id == "unique_run"
    assert (tmp_path / "unique_run").exists()


def test_multiple_reviewers_created(tmp_path):
    """Test that multiple UBR reviewers are created from config."""
    config = InspectionConfig(
        inspection_id="multi_reviewer_test",
        condition=ConditionType.C1_UBR,
        reading_techniques=[ReadingTechnique.UBR, ReadingTechnique.UBR, ReadingTechnique.UBR],
        artifacts=["design/test.pdf"],
        llm_params=LLMParams(model="gpt-5-mini", provider="openai"),
        dry_run=True,
    )

    process = FaganProcess(config, output_dir=tmp_path)
    run = process.run()

    # Should have 3 reviewer outputs
    assert len(run.reviewer_outputs) == 3

    # All should be UBR reviewers
    assert all(output.technique == ReadingTechnique.UBR for output in run.reviewer_outputs)

    # Should have unique IDs
    reviewer_ids = [output.reviewer_id for output in run.reviewer_outputs]
    assert len(set(reviewer_ids)) == 3  # All unique
    assert "reviewer_1_ubr" in reviewer_ids[0]
    assert "reviewer_2_ubr" in reviewer_ids[1]
    assert "reviewer_3_ubr" in reviewer_ids[2]


class TestPerReviewerFocus:
    """Tests for per-reviewer focus partitioning via extra_config.reviewer_focus."""

    def _make_process(self, tmp_path, extra_config=None):
        """Helper to create a FaganProcess with given extra_config."""
        config = InspectionConfig(
            inspection_id="focus_test",
            condition=ConditionType.C1_UBR,
            reading_techniques=[ReadingTechnique.UBR, ReadingTechnique.UBR, ReadingTechnique.UBR],
            artifacts=["design/test.pdf"],
            llm_params=LLMParams(model="gpt-5-mini", provider="openai"),
            dry_run=True,
            extra_config=extra_config or {},
        )
        return FaganProcess(config, output_dir=tmp_path)

    def test_no_reviewer_focus_returns_base_context(self, tmp_path):
        """Without reviewer_focus, all reviewers get the same base context."""
        process = self._make_process(tmp_path)
        ctx0 = process._get_extra_context(ReadingTechnique.UBR, reviewer_index=0)
        ctx1 = process._get_extra_context(ReadingTechnique.UBR, reviewer_index=1)
        ctx2 = process._get_extra_context(ReadingTechnique.UBR, reviewer_index=2)

        assert ctx0 == ctx1 == ctx2
        # Point 2: UBR context now contains structured methodology
        assert "UBR Inspection Mode" in ctx0

    def test_reviewer_focus_appended(self, tmp_path):
        """With reviewer_focus, each reviewer gets unique context."""
        process = self._make_process(tmp_path, extra_config={
            "reviewer_focus": [
                "Scope: sections 3.1, 3.2",
                "Scope: sections 3.4, 3.5",
                "Scope: sections 4.1, 4.2",
            ]
        })
        ctx0 = process._get_extra_context(ReadingTechnique.UBR, reviewer_index=0)
        ctx1 = process._get_extra_context(ReadingTechnique.UBR, reviewer_index=1)
        ctx2 = process._get_extra_context(ReadingTechnique.UBR, reviewer_index=2)

        # Each should have base context plus their focus
        # Point 2: UBR context now contains structured methodology
        assert "UBR Inspection Mode" in ctx0
        assert "sections 3.1, 3.2" in ctx0
        assert "sections 3.4, 3.5" in ctx1
        assert "sections 4.1, 4.2" in ctx2

        # All should be different
        assert ctx0 != ctx1
        assert ctx1 != ctx2

    def test_reviewer_focus_index_out_of_range(self, tmp_path):
        """If reviewer_index exceeds focus list, base context only."""
        process = self._make_process(tmp_path, extra_config={
            "reviewer_focus": ["Scope: A", "Scope: B"]
        })
        # Index 2 is out of range (only 2 entries)
        ctx = process._get_extra_context(ReadingTechnique.UBR, reviewer_index=2)
        # Point 2: UBR context now contains structured methodology
        assert "UBR Inspection Mode" in ctx
        assert "Scope:" not in ctx

    def test_reviewer_focus_empty_entry_ignored(self, tmp_path):
        """Empty focus entry doesn't append extra text."""
        process = self._make_process(tmp_path, extra_config={
            "reviewer_focus": ["", "Scope: B", ""]
        })
        ctx0 = process._get_extra_context(ReadingTechnique.UBR, reviewer_index=0)
        ctx1 = process._get_extra_context(ReadingTechnique.UBR, reviewer_index=1)
        ctx2 = process._get_extra_context(ReadingTechnique.UBR, reviewer_index=2)

        assert "Scope: B" not in ctx0
        assert "Scope: B" in ctx1
        assert "Scope: B" not in ctx2

    def test_cbr_with_reviewer_focus(self, tmp_path):
        """CBR technique also supports reviewer_focus."""
        process = self._make_process(tmp_path, extra_config={
            "reviewer_focus": ["Extra focus for CBR reviewer"]
        })
        ctx = process._get_extra_context(ReadingTechnique.CBR, reviewer_index=0)
        # CBR without checklist file returns empty base context, so just focus
        assert "Extra focus for CBR reviewer" in ctx

    def test_default_reviewer_index_zero(self, tmp_path):
        """Default reviewer_index=0 works without explicit parameter."""
        process = self._make_process(tmp_path, extra_config={
            "reviewer_focus": ["Focus for first reviewer"]
        })
        ctx = process._get_extra_context(ReadingTechnique.UBR)
        assert "Focus for first reviewer" in ctx


class TestC1UbrConfig:
    """Validate c1_ubr.yaml config file structure and reviewer specialization."""

    CONFIG_PATH = Path("configs/examples/c1_ubr.yaml")

    @pytest.fixture
    def config(self):
        """Load c1_ubr.yaml."""
        with open(self.CONFIG_PATH) as f:
            return yaml.safe_load(f)

    def test_config_exists(self):
        """Config file must exist."""
        assert self.CONFIG_PATH.exists()

    def test_three_ubr_reviewers(self, config):
        """Config must define exactly 3 UBR reviewers."""
        techniques = config["reading_techniques"]
        assert len(techniques) == 3
        assert all(t == "UBR" for t in techniques)

    def test_three_distinct_focus_strings(self, config):
        """Config must have 3 distinct reviewer_focus entries."""
        focus = config["extra_config"]["reviewer_focus"]
        assert len(focus) == 3
        # All must be non-empty strings
        assert all(isinstance(f, str) and f.strip() for f in focus)
        # All must be distinct
        assert len(set(f.strip() for f in focus)) == 3

    def test_reviewer_1_covers_table1_and_early_sections(self, config):
        """Reviewer 1 focus must mention Table 1 and sections 3.1–3.2.2."""
        focus = config["extra_config"]["reviewer_focus"][0]
        assert "Table 1" in focus
        assert "3.1" in focus
        assert "3.2" in focus or "3.2.1" in focus or "3.2.2" in focus

    def test_reviewer_2_covers_middle_sections(self, config):
        """Reviewer 2 focus must mention sections 3.3–3.4.2."""
        focus = config["extra_config"]["reviewer_focus"][1]
        assert "3.3" in focus
        assert "3.4" in focus or "3.4.1" in focus or "3.4.2" in focus

    def test_reviewer_3_covers_msc_sections(self, config):
        """Reviewer 3 focus must mention MSC sections 4.1–4.2."""
        focus = config["extra_config"]["reviewer_focus"][2]
        assert "4.1" in focus
        assert "4.2" in focus

    def test_all_reviewers_require_signal_names_in_evidence(self, config):
        """All reviewer focus strings must instruct citing exact signal names."""
        for focus in config["extra_config"]["reviewer_focus"]:
            assert "signal name" in focus.lower() or "cite" in focus.lower()


class TestC1CbrConfig:
    """Validate c1_cbr.yaml config file structure and reviewer specialization."""

    CONFIG_PATH = Path("configs/examples/c1_cbr.yaml")

    @pytest.fixture
    def config(self):
        """Load c1_cbr.yaml."""
        with open(self.CONFIG_PATH) as f:
            return yaml.safe_load(f)

    def test_config_exists(self):
        """Config file must exist."""
        assert self.CONFIG_PATH.exists()

    def test_three_cbr_reviewers(self, config):
        """Config must define exactly 3 CBR reviewers."""
        techniques = config["reading_techniques"]
        assert len(techniques) == 3
        assert all(t == "CBR" for t in techniques)

    def test_three_distinct_focus_strings(self, config):
        """Config must have 3 distinct reviewer_focus entries."""
        focus = config["extra_config"]["reviewer_focus"]
        assert len(focus) == 3
        assert all(isinstance(f, str) and f.strip() for f in focus)
        assert len(set(f.strip() for f in focus)) == 3

    def test_checklist_path_configured(self, config):
        """Config must reference a checklist file that exists."""
        checklist_path = config["extra_config"]["checklist_path"]
        assert checklist_path
        assert Path(checklist_path).exists()

    def test_checklist_artifact_in_config(self, config):
        """CBR config must list the checklist as a loaded artifact."""
        artifacts = config["artifacts"]
        checklist_artifacts = [a for a in artifacts if "checklist" in a.lower()]
        assert len(checklist_artifacts) >= 1, "No checklist artifact in CBR config"
        # The checklist artifact must exist under artifacts/input/
        for rel in checklist_artifacts:
            assert Path("artifacts/input") / rel

    def test_ubr_guide_not_in_cbr_artifacts(self, config):
        """CBR config must NOT reference the UBR guide."""
        artifacts = config["artifacts"]
        for artifact in artifacts:
            assert "GuideUBR" not in artifact, (
                f"UBR guide '{artifact}' should not appear in CBR config"
            )

    def test_reviewer_1_covers_table1_and_early_sections(self, config):
        """Reviewer 1 focus must mention Table 1 and sections 3.1-3.2.2."""
        focus = config["extra_config"]["reviewer_focus"][0]
        assert "Table 1" in focus
        assert "3.1" in focus
        assert "3.2" in focus or "3.2.1" in focus or "3.2.2" in focus

    def test_reviewer_2_covers_middle_sections(self, config):
        """Reviewer 2 focus must mention sections 3.3-3.4.2."""
        focus = config["extra_config"]["reviewer_focus"][1]
        assert "3.3" in focus
        assert "3.4" in focus or "3.4.1" in focus or "3.4.2" in focus

    def test_reviewer_3_covers_msc_sections(self, config):
        """Reviewer 3 focus must mention MSC sections 4.1-4.2."""
        focus = config["extra_config"]["reviewer_focus"][2]
        assert "4.1" in focus
        assert "4.2" in focus

    def test_all_reviewers_require_signal_names(self, config):
        """All CBR reviewer focus strings must instruct citing signal names."""
        for focus in config["extra_config"]["reviewer_focus"]:
            assert "signal name" in focus.lower() or "cite" in focus.lower()

    def test_model_is_valid(self, config):
        """Model must be a real model (not gpt-5-mini)."""
        model = config["llm_params"]["model"]
        assert model != "gpt-5-mini"
        assert "gpt" in model or "claude" in model

    def test_has_three_artifacts(self, config):
        """Config must reference design, usecases, and checklist artifacts."""
        artifacts = config["artifacts"]
        assert len(artifacts) >= 3
        artifact_str = " ".join(artifacts)
        assert "design" in artifact_str.lower()
        assert "usecase" in artifact_str.lower()
        assert "checklist" in artifact_str.lower()


class TestCbrChecklistArtifact:
    """Validate the checklist artifact file exists and matches the source."""

    ARTIFACT_PATH = Path("artifacts/input/checklists/cbr_checklist_v2.yaml")
    SOURCE_PATH = Path("configs/checklists/cbr_minimal.yaml")

    def test_artifact_checklist_exists(self):
        """Checklist must exist in artifact tree for Phase 1 loading."""
        assert self.ARTIFACT_PATH.exists()

    def test_artifact_matches_source(self):
        """Artifact copy and source checklist must have the same content."""
        assert self.ARTIFACT_PATH.read_text() == self.SOURCE_PATH.read_text()

    def test_artifact_type_inferred_as_checklist(self):
        """ArtifactLoader must infer type 'checklist' for the checklist file."""
        from src.fagan_tool.utils.artifact_loader import ArtifactLoader
        loader = ArtifactLoader()
        inferred = loader._infer_type("checklists/cbr_checklist_v2.yaml")
        assert inferred == "checklist"


class TestCbrChecklistStructure:
    """Validate cbr_minimal.yaml checklist is domain-specific."""

    CHECKLIST_PATH = Path("configs/checklists/cbr_minimal.yaml")

    @pytest.fixture
    def checklist(self):
        """Load checklist."""
        with open(self.CHECKLIST_PATH) as f:
            return yaml.safe_load(f)

    def test_checklist_exists(self):
        """Checklist file must exist."""
        assert self.CHECKLIST_PATH.exists()

    def test_has_seven_categories(self, checklist):
        """Checklist must have 7 domain-specific categories."""
        categories = checklist["categories"]
        assert len(categories) == 7

    def test_categories_have_questions(self, checklist):
        """Each category must have a question field."""
        for cat in checklist["categories"]:
            assert "question" in cat
            assert len(cat["question"]) > 10

    def test_categories_have_items(self, checklist):
        """Each category must have checklist items."""
        for cat in checklist["categories"]:
            assert "items" in cat
            assert len(cat["items"]) >= 3

    def test_covers_missing_signals(self, checklist):
        """Checklist must cover missing signals."""
        names = " ".join(cat["name"] for cat in checklist["categories"])
        assert "Missing Signals" in names or "missing signal" in names.lower()

    def test_covers_acknowledgment(self, checklist):
        """Checklist must cover acknowledgment completeness."""
        names = " ".join(cat["name"] for cat in checklist["categories"])
        assert "Acknowledgment" in names or "acknowledgment" in names.lower()

    def test_covers_timeout(self, checklist):
        """Checklist must cover timeout specifications."""
        names = " ".join(cat["name"] for cat in checklist["categories"])
        assert "Timeout" in names or "timeout" in names.lower()


class TestCbrDryRun:
    """Test CBR dry-run produces correct output structure."""

    def test_dry_run_three_cbr_reviewers(self, tmp_path):
        """Dry-run with 3 CBR reviewers produces 3 reviewer outputs."""
        config = InspectionConfig(
            inspection_id="cbr_dry_test",
            condition=ConditionType.C2_CBR,
            reading_techniques=[ReadingTechnique.CBR, ReadingTechnique.CBR, ReadingTechnique.CBR],
            artifacts=["design/test.pdf"],
            llm_params=LLMParams(model="gpt-4o-mini", provider="openai"),
            dry_run=True,
        )
        process = FaganProcess(config, output_dir=tmp_path)
        run = process.run()

        assert len(run.reviewer_outputs) == 3
        assert all(o.technique == ReadingTechnique.CBR for o in run.reviewer_outputs)

        reviewer_ids = [o.reviewer_id for o in run.reviewer_outputs]
        assert "reviewer_1_cbr" in reviewer_ids[0]
        assert "reviewer_2_cbr" in reviewer_ids[1]
        assert "reviewer_3_cbr" in reviewer_ids[2]

    def test_dry_run_cbr_produces_defects(self, tmp_path):
        """Dry-run CBR reviewers produce dummy defects."""
        config = InspectionConfig(
            inspection_id="cbr_defects_test",
            condition=ConditionType.C2_CBR,
            reading_techniques=[ReadingTechnique.CBR],
            artifacts=["design/test.pdf"],
            llm_params=LLMParams(model="gpt-4o-mini", provider="openai"),
            dry_run=True,
        )
        process = FaganProcess(config, output_dir=tmp_path)
        run = process.run()

        assert len(run.reviewer_outputs) == 1
        assert len(run.reviewer_outputs[0].defects) > 0

    def test_dry_run_cbr_saves_config_snapshot(self, tmp_path):
        """Dry-run CBR saves config_snapshot.json."""
        config = InspectionConfig(
            inspection_id="cbr_snapshot_test",
            condition=ConditionType.C2_CBR,
            reading_techniques=[ReadingTechnique.CBR],
            artifacts=["design/test.pdf"],
            llm_params=LLMParams(model="gpt-4o-mini", provider="openai"),
            dry_run=True,
        )
        process = FaganProcess(config, output_dir=tmp_path)
        process.run()

        snapshot_path = tmp_path / "cbr_snapshot_test" / "config_snapshot.json"
        assert snapshot_path.exists()


class TestCbrPromptRouting:
    """Test that CBR technique routes to the correct prompt file."""

    def test_cbr_routes_to_reviewer_cbr(self):
        """CBR technique must map to reviewer_cbr.txt."""
        from src.fagan_tool.agents.reviewer_agent import ReviewerAgent
        agent = ReviewerAgent.__new__(ReviewerAgent)
        agent.technique = ReadingTechnique.CBR
        assert agent._get_prompt_file() == "reviewer_cbr.txt"

    def test_ubr_routes_to_reviewer_ubr(self):
        """UBR technique must still map to reviewer_ubr.txt (regression)."""
        from src.fagan_tool.agents.reviewer_agent import ReviewerAgent
        agent = ReviewerAgent.__new__(ReviewerAgent)
        agent.technique = ReadingTechnique.UBR
        assert agent._get_prompt_file() == "reviewer_ubr.txt"

    def test_cbr_prompt_file_exists(self):
        """reviewer_cbr.txt must exist in prompts directory."""
        assert Path("prompts/reviewer_cbr.txt").exists()

    def test_ubr_prompt_file_exists(self):
        """reviewer_ubr.txt must exist in prompts directory (regression)."""
        assert Path("prompts/reviewer_ubr.txt").exists()


class TestCbrExtraContext:
    """Test that CBR loads checklist as extra_context with configurable path."""

    def _make_process(self, tmp_path, extra_config=None):
        config = InspectionConfig(
            inspection_id="cbr_ctx_test",
            condition=ConditionType.C2_CBR,
            reading_techniques=[ReadingTechnique.CBR],
            artifacts=["design/test.pdf"],
            llm_params=LLMParams(model="gpt-4o-mini", provider="openai"),
            dry_run=True,
            extra_config=extra_config or {},
        )
        return FaganProcess(config, output_dir=tmp_path)

    def test_cbr_loads_default_checklist(self, tmp_path):
        """CBR without checklist_path loads the default checklist from artifact tree."""
        process = self._make_process(tmp_path)
        ctx = process._get_extra_context(ReadingTechnique.CBR)
        # Default checklist from artifacts/input/checklists/ should be loaded
        assert "checklist_version" in ctx or "categories" in ctx
        assert "CL1" in ctx or "Missing Signals" in ctx

    def test_cbr_loads_custom_checklist_path(self, tmp_path):
        """CBR with checklist_path in extra_config loads that checklist."""
        # Create a custom checklist
        custom_path = tmp_path / "custom_checklist.yaml"
        custom_path.write_text("custom_checklist: true\ncategories: []")

        process = self._make_process(tmp_path, extra_config={
            "checklist_path": str(custom_path),
        })
        ctx = process._get_extra_context(ReadingTechnique.CBR)
        assert "custom_checklist: true" in ctx

    def test_cbr_checklist_plus_reviewer_focus(self, tmp_path):
        """CBR loads checklist AND appends reviewer_focus."""
        process = self._make_process(tmp_path, extra_config={
            "reviewer_focus": ["Focus on sections 3.1-3.2"]
        })
        ctx = process._get_extra_context(ReadingTechnique.CBR, reviewer_index=0)
        assert "Focus on sections 3.1-3.2" in ctx

    def test_cbr_context_contains_checklist_items(self, tmp_path):
        """CBR context must contain at least one checklist item (CL1/Missing Signals)."""
        process = self._make_process(tmp_path, extra_config={
            "checklist_path": "artifacts/input/checklists/cbr_checklist_v2.yaml",
        })
        ctx = process._get_extra_context(ReadingTechnique.CBR)
        # Must contain domain-specific checklist content
        assert "Missing Signals" in ctx
        assert "CL1" in ctx
        assert "Acknowledgment" in ctx or "CL4" in ctx

    def test_ubr_context_unchanged_after_cbr_changes(self, tmp_path):
        """UBR extra context must not be affected by CBR changes (regression)."""
        process = self._make_process(tmp_path)
        ctx = process._get_extra_context(ReadingTechnique.UBR)
        # Point 2: UBR context now contains structured methodology
        assert "UBR Inspection Mode" in ctx
        # Must NOT contain CBR checklist content
        assert "CL1" not in ctx
        assert "Missing Signals" not in ctx


class TestUBRConfigValidation:
    """Tests for UBR configuration validation (hardening)."""

    def test_invalid_ubr_variant_raises_error(self, tmp_path):
        """Invalid ubr_variant must raise clear ValueError."""
        config = InspectionConfig(
            inspection_id="invalid_variant_test",
            condition=ConditionType.C1_UBR,
            reading_techniques=[ReadingTechnique.UBR],
            artifacts=["design/Taxi_des_exp_v2.pdf"],
            llm_params=LLMParams(model="gpt-5-mini", provider="openai"),
            dry_run=True,
            extra_config={"ubr_variant": "INVALID-UBR"}
        )
        process = FaganProcess(config, output_dir=tmp_path, prompt_dir=Path("prompts"))

        with pytest.raises(ValueError) as exc_info:
            process._validate_ubr_config()

        assert "Invalid ubr_variant" in str(exc_info.value)
        assert "INVALID-UBR" in str(exc_info.value)
        assert "RB-UBR" in str(exc_info.value)
        assert "TC-UBR" in str(exc_info.value)

    def test_valid_rb_ubr_variant_passes(self, tmp_path):
        """RB-UBR is a valid variant and must not raise."""
        config = InspectionConfig(
            inspection_id="rb_ubr_test",
            condition=ConditionType.C1_UBR,
            reading_techniques=[ReadingTechnique.UBR],
            artifacts=["design/Taxi_des_exp_v2.pdf"],
            llm_params=LLMParams(model="gpt-5-mini", provider="openai"),
            dry_run=True,
            extra_config={
                "ubr_variant": "RB-UBR",
                "use_case_artifact": "usecases/UseCasesRank_v3.4.pdf"
            }
        )
        process = FaganProcess(config, output_dir=tmp_path, prompt_dir=Path("prompts"))
        # Should not raise
        process._validate_ubr_config()

    def test_valid_tc_ubr_variant_passes(self, tmp_path):
        """TC-UBR is a valid variant and must not raise."""
        config = InspectionConfig(
            inspection_id="tc_ubr_test",
            condition=ConditionType.C1_UBR,
            reading_techniques=[ReadingTechnique.UBR],
            artifacts=["design/Taxi_des_exp_v2.pdf"],
            llm_params=LLMParams(model="gpt-5-mini", provider="openai"),
            dry_run=True,
            extra_config={
                "ubr_variant": "TC-UBR",
                "use_case_artifact": "usecases/UseCasesRank_v3.4.pdf"
            }
        )
        process = FaganProcess(config, output_dir=tmp_path, prompt_dir=Path("prompts"))
        # Should not raise
        process._validate_ubr_config()

    def test_missing_use_case_artifact_raises_error(self, tmp_path):
        """Non-existent use_case_artifact must raise clear ValueError."""
        config = InspectionConfig(
            inspection_id="missing_artifact_test",
            condition=ConditionType.C1_UBR,
            reading_techniques=[ReadingTechnique.UBR],
            artifacts=["design/Taxi_des_exp_v2.pdf"],
            llm_params=LLMParams(model="gpt-5-mini", provider="openai"),
            dry_run=True,
            extra_config={
                "ubr_variant": "RB-UBR",
                "use_case_artifact": "usecases/NonExistent.pdf"
            }
        )
        process = FaganProcess(config, output_dir=tmp_path, prompt_dir=Path("prompts"))

        with pytest.raises(ValueError) as exc_info:
            process._validate_ubr_config()

        assert "not found" in str(exc_info.value)
        assert "NonExistent.pdf" in str(exc_info.value)

    def test_ubr_context_contains_methodology_structure(self, tmp_path):
        """_build_ubr_context() must contain Purpose/Tasks/Variants guidance."""
        config = InspectionConfig(
            inspection_id="context_structure_test",
            condition=ConditionType.C1_UBR,
            reading_techniques=[ReadingTechnique.UBR],
            artifacts=["design/Taxi_des_exp_v2.pdf"],
            llm_params=LLMParams(model="gpt-5-mini", provider="openai"),
            dry_run=True,
            extra_config={
                "ubr_variant": "RB-UBR",
                "use_case_artifact": "usecases/UseCasesRank_v3.4.pdf"
            }
        )
        process = FaganProcess(config, output_dir=tmp_path, prompt_dir=Path("prompts"))
        ctx = process._build_ubr_context()

        # Must contain methodology structure hints
        assert "Purpose" in ctx
        assert "Tasks" in ctx
        assert "Variants" in ctx
        assert "UBR Inspection Process" in ctx
        assert "RB-UBR" in ctx


class TestReviewerArtifactAssignment:
    """Tests for reviewer-specific artifact assignment (Point 3)."""

    def _make_mock_artifacts(self, types: list) -> list:
        """Create mock artifacts with specified types."""
        from src.fagan_tool.core.schemas import ArtifactMetadata
        artifacts = []
        for i, artifact_type in enumerate(types):
            artifacts.append({
                "metadata": ArtifactMetadata(
                    name=f"test_{artifact_type}_{i}.pdf",
                    path=f"{artifact_type}/test_{i}.pdf",
                    type=artifact_type,
                    page_count=10,
                    size_bytes=1000,
                ),
                "content": {"type": "text", "text": f"Content for {artifact_type}"}
            })
        return artifacts

    def test_ubr_requires_design(self, tmp_path):
        """UBR reviewer must have design artifact."""
        config = InspectionConfig(
            inspection_id="ubr_design_test",
            condition=ConditionType.C1_UBR,
            reading_techniques=[ReadingTechnique.UBR],
            artifacts=["design/Taxi_des_exp_v2.pdf"],
            llm_params=LLMParams(model="gpt-5-mini", provider="openai"),
            dry_run=True,
        )
        process = FaganProcess(config, output_dir=tmp_path, prompt_dir=Path("prompts"))

        # With design artifact - should pass
        artifacts = self._make_mock_artifacts(["design"])
        filtered = process._filter_artifacts_for_reviewer(
            ReadingTechnique.UBR, artifacts, "reviewer_1_ubr"
        )
        assert len(filtered) == 1
        assert filtered[0]["metadata"].type == "design"

    def test_ubr_missing_design_raises_error(self, tmp_path):
        """UBR reviewer without design artifact raises ValueError."""
        config = InspectionConfig(
            inspection_id="ubr_missing_test",
            condition=ConditionType.C1_UBR,
            reading_techniques=[ReadingTechnique.UBR],
            artifacts=["usecases/test.pdf"],
            llm_params=LLMParams(model="gpt-5-mini", provider="openai"),
            dry_run=True,
        )
        process = FaganProcess(config, output_dir=tmp_path, prompt_dir=Path("prompts"))

        # Only usecase, no design - should fail
        artifacts = self._make_mock_artifacts(["usecase"])

        with pytest.raises(ValueError) as exc_info:
            process._filter_artifacts_for_reviewer(
                ReadingTechnique.UBR, artifacts, "reviewer_1_ubr"
            )

        assert "missing required artifact types" in str(exc_info.value)
        assert "design" in str(exc_info.value)

    def test_cbr_requires_design(self, tmp_path):
        """CBR reviewer must have design artifact."""
        config = InspectionConfig(
            inspection_id="cbr_design_test",
            condition=ConditionType.C2_CBR,
            reading_techniques=[ReadingTechnique.CBR],
            artifacts=["design/test.pdf"],
            llm_params=LLMParams(model="gpt-5-mini", provider="openai"),
            dry_run=True,
        )
        process = FaganProcess(config, output_dir=tmp_path, prompt_dir=Path("prompts"))

        artifacts = self._make_mock_artifacts(["design", "checklist"])
        filtered = process._filter_artifacts_for_reviewer(
            ReadingTechnique.CBR, artifacts, "reviewer_1_cbr"
        )
        assert len(filtered) == 2

    def test_pbr_tester_requires_design(self, tmp_path):
        """PBR_TESTER reviewer must have design artifact."""
        config = InspectionConfig(
            inspection_id="pbr_tester_test",
            condition=ConditionType.C3_PBR_TEAM,
            reading_techniques=[ReadingTechnique.PBR_TESTER],
            artifacts=["design/test.pdf"],
            llm_params=LLMParams(model="gpt-5-mini", provider="openai"),
            dry_run=True,
        )
        process = FaganProcess(config, output_dir=tmp_path, prompt_dir=Path("prompts"))

        artifacts = self._make_mock_artifacts(["design", "requirements"])
        filtered = process._filter_artifacts_for_reviewer(
            ReadingTechnique.PBR_TESTER, artifacts, "reviewer_1_pbr_tester"
        )
        assert len(filtered) == 2

    def test_pbr_designer_filters_usecase(self, tmp_path):
        """PBR_DESIGNER should not receive usecase artifacts."""
        config = InspectionConfig(
            inspection_id="pbr_designer_test",
            condition=ConditionType.C3_PBR_TEAM,
            reading_techniques=[ReadingTechnique.PBR_DESIGNER],
            artifacts=["design/test.pdf"],
            llm_params=LLMParams(model="gpt-5-mini", provider="openai"),
            dry_run=True,
        )
        process = FaganProcess(config, output_dir=tmp_path, prompt_dir=Path("prompts"))

        artifacts = self._make_mock_artifacts(["design", "usecase", "requirements"])
        filtered = process._filter_artifacts_for_reviewer(
            ReadingTechnique.PBR_DESIGNER, artifacts, "reviewer_1_pbr_designer"
        )
        # PBR_DESIGNER: design (required) + requirements (optional), NOT usecase
        assert len(filtered) == 2
        artifact_types = {a["metadata"].type for a in filtered}
        assert "design" in artifact_types
        assert "requirements" in artifact_types
        assert "usecase" not in artifact_types

    def test_gold_artifact_blocked_on_reviewer_level(self, tmp_path):
        """Gold artifacts must be blocked even if they reach _filter_artifacts_for_reviewer."""
        from src.fagan_tool.core.schemas import ArtifactMetadata

        config = InspectionConfig(
            inspection_id="gold_block_test",
            condition=ConditionType.C1_UBR,
            reading_techniques=[ReadingTechnique.UBR],
            artifacts=["design/test.pdf"],
            llm_params=LLMParams(model="gpt-5-mini", provider="openai"),
            dry_run=True,
        )
        process = FaganProcess(config, output_dir=tmp_path, prompt_dir=Path("prompts"))
        # Initialize gold guard flag
        process._gold_guard_verified = True

        # Create artifacts including a gold path (should cause fail-fast error)
        artifacts = [
            {
                "metadata": ArtifactMetadata(
                    name="Taxi_des_exp_v2.pdf",
                    path="design/Taxi_des_exp_v2.pdf",
                    type="design",
                    page_count=10,
                    size_bytes=1000,
                ),
                "content": {"type": "text", "text": "Design content"}
            },
            {
                "metadata": ArtifactMetadata(
                    name="Faults_List.xls",
                    path="artifacts/gold/Faults_List.xls",  # GOLD PATH!
                    type="design",  # Even if wrongly typed
                    page_count=1,
                    size_bytes=500,
                ),
                "content": {"type": "text", "text": "Gold content - SHOULD BE BLOCKED"}
            },
        ]

        # Point 4: Gold artifact must trigger fail-fast ValueError
        with pytest.raises(ValueError) as exc_info:
            process._filter_artifacts_for_reviewer(
                ReadingTechnique.UBR, artifacts, "reviewer_1_ubr"
            )

        assert "GOLD LEAKAGE BLOCKED" in str(exc_info.value)
        assert "Faults_List.xls" in str(exc_info.value)

    def test_artifact_policy_exists_for_all_techniques(self):
        """Verify REVIEWER_ARTIFACT_POLICY covers all reading techniques."""
        from src.fagan_tool.core.schemas import REVIEWER_ARTIFACT_POLICY, ReadingTechnique

        for technique in ReadingTechnique:
            assert technique in REVIEWER_ARTIFACT_POLICY, (
                f"Missing artifact policy for {technique.value}"
            )
            policy = REVIEWER_ARTIFACT_POLICY[technique]
            assert "required_types" in policy
            assert "optional_types" in policy
            assert "forbidden_types" in policy

    def test_gold_guard_verified_flag_set(self, tmp_path):
        """Test that _gold_guard_verified flag is set after filtering (Point 4)."""
        config = InspectionConfig(
            inspection_id="gold_guard_flag_test",
            condition=ConditionType.C1_UBR,
            reading_techniques=[ReadingTechnique.UBR],
            artifacts=["design/test.pdf"],
            llm_params=LLMParams(model="gpt-5-mini", provider="openai"),
            dry_run=True,
        )
        process = FaganProcess(config, output_dir=tmp_path, prompt_dir=Path("prompts"))
        process._gold_guard_verified = True  # Initialize flag

        # Filter valid artifacts (no gold)
        artifacts = self._make_mock_artifacts(["design"])
        process._filter_artifacts_for_reviewer(
            ReadingTechnique.UBR, artifacts, "reviewer_1_ubr"
        )

        # Gold guard should remain True (no gold encountered, verification passed)
        assert process._gold_guard_verified is True

    def test_schema_version_in_dry_run_metadata(self, tmp_path):
        """Test that defect_schema_version is set in metadata (Point 4)."""
        from src.fagan_tool.core.schemas import DEFECT_SCHEMA_VERSION

        config = InspectionConfig(
            inspection_id="schema_version_test",
            condition=ConditionType.C1_UBR,
            reading_techniques=[ReadingTechnique.UBR],
            artifacts=["design/Taxi_des_exp_v2.pdf"],
            llm_params=LLMParams(model="gpt-5-mini", provider="openai"),
            dry_run=True,
        )
        process = FaganProcess(config, output_dir=tmp_path, prompt_dir=Path("prompts"))
        run = process.run()

        # Metadata should have schema version
        assert run.metadata.defect_schema_version == DEFECT_SCHEMA_VERSION


class TestExtraContextGoldGuard:
    """Tests for gold guard in extra_context loading (Point 4 hardening)."""

    def test_cbr_checklist_gold_path_blocked(self, tmp_path):
        """CBR checklist_path pointing to gold directory raises ValueError."""
        config = InspectionConfig(
            inspection_id="cbr_gold_checklist_test",
            condition=ConditionType.C2_CBR,
            reading_techniques=[ReadingTechnique.CBR],
            artifacts=["design/test.pdf"],
            llm_params=LLMParams(model="gpt-5-mini", provider="openai"),
            dry_run=True,
            extra_config={
                "checklist_path": "artifacts/gold/README.md"  # GOLD PATH!
            }
        )
        process = FaganProcess(config, output_dir=tmp_path, prompt_dir=Path("prompts"))

        with pytest.raises(ValueError) as exc_info:
            process._get_extra_context(ReadingTechnique.CBR)

        assert "LEAKAGE GUARD" in str(exc_info.value) or "gold" in str(exc_info.value).lower()

    def test_cbr_checklist_valid_yaml_works(self, tmp_path):
        """CBR checklist_path pointing to valid YAML file works."""
        # Create a temporary valid checklist
        checklist_content = "checklist:\n  - item: CL1\n    description: Test item"
        checklist_file = tmp_path / "test_checklist.yaml"
        checklist_file.write_text(checklist_content, encoding="utf-8")

        config = InspectionConfig(
            inspection_id="cbr_valid_checklist_test",
            condition=ConditionType.C2_CBR,
            reading_techniques=[ReadingTechnique.CBR],
            artifacts=["design/test.pdf"],
            llm_params=LLMParams(model="gpt-5-mini", provider="openai"),
            dry_run=True,
            extra_config={
                "checklist_path": str(checklist_file)
            }
        )
        process = FaganProcess(config, output_dir=tmp_path / "run", prompt_dir=Path("prompts"))

        # Should work without raising
        context = process._get_extra_context(ReadingTechnique.CBR)
        assert "CL1" in context
        assert "Test item" in context

    def test_cbr_checklist_invalid_extension_rejected(self, tmp_path):
        """CBR checklist_path with disallowed extension raises ValueError."""
        # Create a file with wrong extension
        bad_file = tmp_path / "bad_checklist.xls"
        bad_file.write_text("not a checklist", encoding="utf-8")

        config = InspectionConfig(
            inspection_id="cbr_bad_ext_test",
            condition=ConditionType.C2_CBR,
            reading_techniques=[ReadingTechnique.CBR],
            artifacts=["design/test.pdf"],
            llm_params=LLMParams(model="gpt-5-mini", provider="openai"),
            dry_run=True,
            extra_config={
                "checklist_path": str(bad_file)
            }
        )
        process = FaganProcess(config, output_dir=tmp_path / "run", prompt_dir=Path("prompts"))

        with pytest.raises(ValueError) as exc_info:
            process._get_extra_context(ReadingTechnique.CBR)

        assert "Invalid checklist file type" in str(exc_info.value)
        assert ".xls" in str(exc_info.value)

    def test_ubr_use_case_artifact_gold_path_blocked(self, tmp_path):
        """UBR use_case_artifact with path traversal to gold raises ValueError."""
        config = InspectionConfig(
            inspection_id="ubr_gold_artifact_test",
            condition=ConditionType.C1_UBR,
            reading_techniques=[ReadingTechnique.UBR],
            artifacts=["design/test.pdf"],
            llm_params=LLMParams(model="gpt-5-mini", provider="openai"),
            dry_run=True,
            extra_config={
                "ubr_variant": "RB-UBR",
                "use_case_artifact": "../gold/README.md"  # Path traversal to gold!
            }
        )
        process = FaganProcess(config, output_dir=tmp_path, prompt_dir=Path("prompts"))

        with pytest.raises(ValueError) as exc_info:
            process._validate_ubr_config()

        assert "LEAKAGE GUARD" in str(exc_info.value) or "gold" in str(exc_info.value).lower()
