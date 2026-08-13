"""Requirements-document integration: type inference, policy, planning focus.

These tests guard the changes that brought the textual requirements
specification (``artifacts/input/requirements/TextReqSpec_v3.6.pdf``) into
the regular inspection inputs:

* ``ArtifactLoader._infer_type`` must classify paths under ``requirements/``
  as ``"requirements"`` regardless of filename quirks.
* ``REVIEWER_ARTIFACT_POLICY`` for UBR / CBR must accept ``"requirements"``
  artifacts so the reviewer filter does not silently drop them.
* ``_filter_artifacts_for_reviewer`` must include a requirements artifact
  in the UBR and CBR reviewer's filtered list.
* The optional extracted-use-case worklist hook
  (``_render_extracted_use_case_worklist``) must return an empty string
  when the JSON is absent and a populated section when it is present.
* Gold paths must still be rejected (regression — guards must keep
  working).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from fagan_tool.core.process import FaganProcess
from fagan_tool.core.schemas import (
    ArtifactMetadata,
    ConditionType,
    InspectionConfig,
    LLMParams,
    ReadingTechnique,
    REVIEWER_ARTIFACT_POLICY,
)
from fagan_tool.utils.artifact_loader import ArtifactLoader


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_artifact(artifact_type: str, name: str) -> dict:
    return {
        "metadata": ArtifactMetadata(
            name=name,
            path=f"{artifact_type}/{name}",
            type=artifact_type,
            page_count=10,
            size_bytes=1000,
        ),
        "content": {"type": "text", "text": "stub"},
    }


def _make_process(technique: ReadingTechnique, tmp_path: Path) -> FaganProcess:
    config = InspectionConfig(
        inspection_id="req_artifact_test",
        condition=ConditionType.C1_UBR if technique == ReadingTechnique.UBR else ConditionType.C2_CBR,
        reading_techniques=[technique],
        artifacts=["design/Taxi_des_exp_v2.pdf"],
        llm_params=LLMParams(model="gpt-5-mini", provider="openai"),
        dry_run=True,
    )
    proc = FaganProcess(config, output_dir=tmp_path, prompt_dir=Path("prompts"))
    proc._gold_guard_verified = True
    return proc


# ---------------------------------------------------------------------------
# Type inference
# ---------------------------------------------------------------------------


class TestRequirementsTypeInference:
    """The /requirements/ directory must drive the inferred type."""

    def test_requirements_pdf_path(self):
        loader = ArtifactLoader()
        assert loader._infer_type("requirements/TextReqSpec_v3.6.pdf") == "requirements"

    def test_directory_wins_over_ambiguous_filename(self):
        loader = ArtifactLoader()
        # Even if the filename has no obvious keyword, the directory rules.
        assert loader._infer_type("requirements/spec_v1.pdf") == "requirements"

    def test_backslashes_normalised(self):
        loader = ArtifactLoader()
        assert loader._infer_type("requirements\\TextReqSpec_v3.6.pdf") == "requirements"


# ---------------------------------------------------------------------------
# Reviewer policy
# ---------------------------------------------------------------------------


class TestPolicyAllowsRequirements:
    """UBR and CBR policies must permit requirements artifacts."""

    def test_ubr_accepts_requirements(self):
        policy = REVIEWER_ARTIFACT_POLICY[ReadingTechnique.UBR]
        allowed = policy["required_types"] | policy["optional_types"]
        assert "requirements" in allowed

    def test_cbr_accepts_requirements(self):
        policy = REVIEWER_ARTIFACT_POLICY[ReadingTechnique.CBR]
        allowed = policy["required_types"] | policy["optional_types"]
        assert "requirements" in allowed

    def test_filter_passes_requirements_to_ubr(self, tmp_path):
        proc = _make_process(ReadingTechnique.UBR, tmp_path)
        arts = [
            _mock_artifact("design", "design.pdf"),
            _mock_artifact("requirements", "TextReqSpec_v3.6.pdf"),
            _mock_artifact("usecase", "uc.pdf"),
        ]
        filtered = proc._filter_artifacts_for_reviewer(
            ReadingTechnique.UBR, arts, "reviewer_1_ubr"
        )
        types = sorted(a["metadata"].type for a in filtered)
        assert types == ["design", "requirements", "usecase"]

    def test_filter_passes_requirements_to_cbr(self, tmp_path):
        proc = _make_process(ReadingTechnique.CBR, tmp_path)
        arts = [
            _mock_artifact("design", "design.pdf"),
            _mock_artifact("requirements", "TextReqSpec_v3.6.pdf"),
            _mock_artifact("checklist", "checklist.yaml"),
        ]
        filtered = proc._filter_artifacts_for_reviewer(
            ReadingTechnique.CBR, arts, "reviewer_1_cbr"
        )
        types = sorted(a["metadata"].type for a in filtered)
        assert types == ["checklist", "design", "requirements"]


# ---------------------------------------------------------------------------
# Gold leakage regression
# ---------------------------------------------------------------------------


class TestGoldStillBlockedAfterRequirementsAdded:
    """The new requirements rule must not weaken the gold guard."""

    def test_gold_path_blocked_at_filter(self, tmp_path):
        proc = _make_process(ReadingTechnique.UBR, tmp_path)
        gold_art = {
            "metadata": ArtifactMetadata(
                name="Faults_List_In_ver6.xls",
                path="artifacts/gold/Faults_List_In_ver6.xls",
                type="other",
                page_count=None,
                size_bytes=1,
            ),
            "content": {"type": "text", "text": "stub"},
        }
        arts = [_mock_artifact("design", "design.pdf"), gold_art]
        with pytest.raises(ValueError, match="GOLD LEAKAGE BLOCKED"):
            proc._filter_artifacts_for_reviewer(
                ReadingTechnique.UBR, arts, "reviewer_1_ubr"
            )


# ---------------------------------------------------------------------------
# Extracted use-case worklist rendering
# ---------------------------------------------------------------------------


class TestUseCaseWorklistRender:
    """``_render_extracted_use_case_worklist`` is an optional hook."""

    def test_missing_json_returns_empty_string(self, tmp_path):
        proc = _make_process(ReadingTechnique.UBR, tmp_path)
        result = proc._render_extracted_use_case_worklist(tmp_path / "nope.json")
        assert result == ""

    def test_malformed_json_returns_empty_string(self, tmp_path):
        proc = _make_process(ReadingTechnique.UBR, tmp_path)
        bad = tmp_path / "broken.json"
        bad.write_text("not json at all", encoding="utf-8")
        assert proc._render_extracted_use_case_worklist(bad) == ""

    def test_renders_sections_for_each_use_case(self, tmp_path):
        proc = _make_process(ReadingTechnique.UBR, tmp_path)
        payload = {
            "use_cases": [
                {
                    "id": "1.1",
                    "title": "Taxi: Submit order",
                    "tasks": ["A customer wants a taxi.", "Order is entered."],
                    "variants": ["4b No available taxis."],
                },
                {
                    "id": "1.2",
                    "title": "Central: Submit order",
                    "tasks": [],
                    "variants": [],
                },
            ],
            "warnings": [],
        }
        path = tmp_path / "uc.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        rendered = proc._render_extracted_use_case_worklist(path)
        assert "Use Case Worklist (extracted)" in rendered
        assert "1.1" in rendered and "Submit order" in rendered
        assert "Task: A customer wants a taxi." in rendered
        assert "Variant: 4b No available taxis." in rendered
        assert "1.2" in rendered

    def test_warnings_are_surfaced(self, tmp_path):
        proc = _make_process(ReadingTechnique.UBR, tmp_path)
        payload = {
            "use_cases": [{"id": "1.1", "title": "X", "tasks": [], "variants": []}],
            "warnings": ["sample warning"],
        }
        path = tmp_path / "uc.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        rendered = proc._render_extracted_use_case_worklist(path)
        assert "sample warning" in rendered

    def test_default_path_lives_next_to_use_case_pdf(self, tmp_path):
        """Default lookup must point at artifacts/input/usecases/, NOT results/.

        The worklist is an input artefact and lives next to the PDF so that
        runs stay reproducible without writing into results/.
        """
        import inspect
        sig = inspect.signature(FaganProcess._render_extracted_use_case_worklist)
        default = sig.parameters["json_path"].default
        # default is a Path("…") instance; compare as posix string
        assert str(default).replace("\\", "/") == (
            "artifacts/input/usecases/UseCasesRank_v3.4_extracted.json"
        )


# ---------------------------------------------------------------------------
# _build_ubr_context wiring (the WARN-on-missing branch)
# ---------------------------------------------------------------------------


class TestBuildUbrContextWorklist:
    """``_build_ubr_context`` must consume the input-side JSON or warn."""

    def test_worklist_appended_when_input_file_exists(self, tmp_path, monkeypatch):
        # The repo ships the extracted worklist under artifacts/input/usecases/.
        # Copy the real file into a temporary work-tree to keep the test hermetic.
        src = Path("artifacts/input/usecases/UseCasesRank_v3.4_extracted.json")
        if not src.exists():
            pytest.skip(
                "extracted worklist not present in repo; run "
                "scripts/extract_use_cases_rankbased.py once before testing"
            )
        dst_dir = tmp_path / "artifacts" / "input" / "usecases"
        dst_dir.mkdir(parents=True)
        (dst_dir / src.name).write_bytes(src.read_bytes())

        monkeypatch.chdir(tmp_path)
        proc = _make_process(ReadingTechnique.UBR, tmp_path)
        ctx = proc._build_ubr_context()
        assert "Use Case Worklist (extracted)" in ctx

    def test_warn_and_continue_when_input_file_missing(self, tmp_path, monkeypatch, capsys):
        # cd into an empty work-tree so the JSON cannot be found.
        monkeypatch.chdir(tmp_path)
        proc = _make_process(ReadingTechnique.UBR, tmp_path)
        ctx = proc._build_ubr_context()
        # No worklist content
        assert "Use Case Worklist (extracted)" not in ctx
        # Core UBR methodology block must still be present (no crash, no skip)
        assert "UBR Inspection Process" in ctx
        # A user-visible warning telling the user how to fix it.
        captured = capsys.readouterr()
        combined = captured.out + captured.err
        assert "UBR worklist not found" in combined
        assert "extract_use_cases_rankbased.py" in combined
