"""Tests für das LLM-Usage-/Kostenlogging (neue, instrumentierte Runs).

Geprüft wird:
1. Usage-Daten werden geschrieben, wenn die Response Usage enthält.
2. Bei fehlender Usage crasht nichts (usage_available=false).
3. Kostenberechnung ist korrekt und konfigurierbar.
4. duration_seconds wird gesetzt.
5. Goldstandard/Evaluation-Code bleibt unberührt (siehe shasum-Checks im
   Auftrag; hier wird zusätzlich verifiziert, dass das Logging ohne Logger
   ein reiner Pass-through ist).
"""

import csv
from unittest.mock import MagicMock, patch

import pytest

from src.fagan_tool.providers.openai_provider import OpenAIProvider
from src.fagan_tool.utils.usage_logging import (
    DEFAULT_COST_CONFIG,
    USAGE_FIELDS,
    UsageLogger,
    compute_costs,
    extract_usage,
    load_cost_config,
)


def _usage_response(content, prompt_tokens=None, completion_tokens=None,
                    total_tokens=None, with_usage=True):
    """Baut eine gemockte OpenAI-Response mit optionaler Usage."""
    resp = MagicMock()
    choice = MagicMock()
    choice.finish_reason = "stop"
    choice.message.content = content
    choice.message.refusal = None
    resp.choices = [choice]
    if with_usage:
        usage = MagicMock()
        usage.prompt_tokens = prompt_tokens
        usage.completion_tokens = completion_tokens
        usage.total_tokens = total_tokens
        resp.usage = usage
    else:
        resp.usage = None
    return resp


class TestCostComputation:
    def test_costs_with_default_prices(self):
        # 1.000.000 input -> 0.15 ; 1.000.000 output -> 0.60
        in_cost, out_cost, total = compute_costs(1_000_000, 1_000_000, DEFAULT_COST_CONFIG)
        assert in_cost == pytest.approx(0.15)
        assert out_cost == pytest.approx(0.60)
        assert total == pytest.approx(0.75)

    def test_costs_configurable(self):
        cfg = {"input_price_per_1m_tokens": 1.0, "output_price_per_1m_tokens": 2.0}
        in_cost, out_cost, total = compute_costs(500_000, 250_000, cfg)
        assert in_cost == pytest.approx(0.5)
        assert out_cost == pytest.approx(0.5)
        assert total == pytest.approx(1.0)

    def test_costs_none_when_tokens_missing(self):
        assert compute_costs(None, None, DEFAULT_COST_CONFIG) == (None, None, None)


class TestExtractUsage:
    def test_extract_real_usage(self):
        resp = _usage_response("ok", prompt_tokens=10, completion_tokens=5, total_tokens=15)
        assert extract_usage(resp) == (10, 5, 15, True)

    def test_extract_derives_total(self):
        resp = _usage_response("ok", prompt_tokens=10, completion_tokens=5, total_tokens=None)
        assert extract_usage(resp) == (10, 5, 15, True)

    def test_extract_no_usage_object(self):
        resp = _usage_response("ok", with_usage=False)
        assert extract_usage(resp) == (None, None, None, False)

    def test_extract_non_numeric_usage_is_unavailable(self):
        # MagicMock-Attribute (nicht-numerisch) dürfen nicht crashen.
        resp = MagicMock()
        resp.usage = MagicMock()  # prompt_tokens etc. sind MagicMocks
        i, o, t, avail = extract_usage(resp)
        assert avail is False


class TestLoadCostConfig:
    def test_load_real_project_config(self):
        cfg = load_cost_config("configs/llm_costs.yaml")
        assert cfg["model_name"] == "gpt-4o-mini"
        # Kostenbasis: USD-Listenpreise für gpt-4o-mini (reale Tokenusage).
        assert cfg["currency"] == "USD"
        assert cfg["input_price_per_1m_tokens"] == 0.15
        assert cfg["output_price_per_1m_tokens"] == 0.60

    def test_missing_file_falls_back_to_defaults(self):
        cfg = load_cost_config("does/not/exist.yaml")
        assert cfg == DEFAULT_COST_CONFIG


class TestUsageLoggerWriting:
    def test_csv_written_with_usage(self, tmp_path):
        logger = UsageLogger(context={"run_id": "r1", "technique": "UBR"})
        logger.record({
            "call_id": "c1", "model": "gpt-4o-mini",
            "start_time_utc": "2026-01-01T00:00:00+00:00",
            "end_time_utc": "2026-01-01T00:00:01+00:00",
            "duration_seconds": 1.0,
            "input_tokens": 100, "output_tokens": 50, "total_tokens": 150,
            "input_cost": 0.000015, "output_cost": 0.00003, "total_cost": 0.000045,
            "usage_available": "true", "error": "",
        })
        out = tmp_path / "llm_usage.csv"
        logger.write_csv(out)
        rows = list(csv.DictReader(out.open(encoding="utf-8")))
        assert len(rows) == 1
        assert rows[0]["run_id"] == "r1"
        assert rows[0]["technique"] == "UBR"
        assert rows[0]["input_tokens"] == "100"
        assert rows[0]["total_cost"] == "4.5e-05" or float(rows[0]["total_cost"]) == pytest.approx(0.000045)
        # Alle Pflichtspalten vorhanden
        assert set(rows[0].keys()) == set(USAGE_FIELDS)

    def test_append_does_not_overwrite(self, tmp_path):
        out = tmp_path / "global.csv"
        l1 = UsageLogger(context={"run_id": "r1"})
        l1.record({"call_id": "a"})
        l1.write_csv(out, append=True)
        l2 = UsageLogger(context={"run_id": "r2"})
        l2.record({"call_id": "b"})
        l2.write_csv(out, append=True)
        rows = list(csv.DictReader(out.open(encoding="utf-8")))
        assert [r["run_id"] for r in rows] == ["r1", "r2"]


class TestProviderUsageLogging:
    @patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"})
    @patch("src.fagan_tool.providers.openai_provider.OpenAI")
    def test_usage_logged_when_response_has_usage(self, mock_openai_class):
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        mock_client.chat.completions.create.return_value = _usage_response(
            '{"ok": true}', prompt_tokens=120, completion_tokens=30, total_tokens=150
        )
        provider = OpenAIProvider(model="gpt-4o-mini")
        logger = UsageLogger(context={"run_id": "run_x", "technique": "CBR"})
        provider.attach_usage_logger(logger, DEFAULT_COST_CONFIG)

        result = provider.generate([{"role": "user", "content": "hi"}])
        assert result == '{"ok": true}'
        assert len(logger.rows) == 1
        row = logger.rows[0]
        assert row["run_id"] == "run_x"
        assert row["technique"] == "CBR"
        assert row["input_tokens"] == 120
        assert row["output_tokens"] == 30
        assert row["total_tokens"] == 150
        assert row["usage_available"] == "true"
        assert row["model"] == "gpt-4o-mini"
        # Kosten korrekt berechnet
        assert row["input_cost"] == pytest.approx(120 / 1_000_000 * 0.15)
        assert row["output_cost"] == pytest.approx(30 / 1_000_000 * 0.60)
        # duration_seconds gesetzt und nicht-negativ
        assert isinstance(row["duration_seconds"], float)
        assert row["duration_seconds"] >= 0.0
        assert row["error"] == ""
        assert row["call_id"]

    @patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"})
    @patch("src.fagan_tool.providers.openai_provider.OpenAI")
    def test_missing_usage_does_not_crash(self, mock_openai_class):
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        mock_client.chat.completions.create.return_value = _usage_response(
            '{"ok": true}', with_usage=False
        )
        provider = OpenAIProvider(model="gpt-4o-mini")
        logger = UsageLogger(context={"run_id": "run_y"})
        provider.attach_usage_logger(logger, DEFAULT_COST_CONFIG)

        result = provider.generate([{"role": "user", "content": "hi"}])
        assert result == '{"ok": true}'
        assert len(logger.rows) == 1
        row = logger.rows[0]
        assert row["usage_available"] == "false"
        assert row["input_tokens"] == ""   # keine erfundenen Zahlen
        assert row["total_cost"] == ""
        assert row["duration_seconds"] >= 0.0

    @patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"})
    @patch("src.fagan_tool.providers.openai_provider.OpenAI")
    def test_error_is_logged_and_reraised(self, mock_openai_class):
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        mock_client.chat.completions.create.side_effect = RuntimeError("boom")
        provider = OpenAIProvider(model="gpt-4o-mini")
        logger = UsageLogger(context={"run_id": "run_z"})
        provider.attach_usage_logger(logger, DEFAULT_COST_CONFIG)

        with pytest.raises(RuntimeError):
            provider.generate([{"role": "user", "content": "hi"}])
        assert len(logger.rows) == 1
        assert "boom" in logger.rows[0]["error"]
        assert logger.rows[0]["usage_available"] == "false"

    @patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"})
    @patch("src.fagan_tool.providers.openai_provider.OpenAI")
    def test_no_logger_is_pure_passthrough(self, mock_openai_class):
        # Ohne angehängten Logger bleibt das Verhalten unverändert.
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        mock_client.chat.completions.create.return_value = _usage_response("plain")
        provider = OpenAIProvider(model="gpt-4o-mini")
        assert provider.usage_logger is None
        result = provider.generate([{"role": "user", "content": "hi"}])
        assert result == "plain"


class TestContextFlow:
    """Kontextfelder run_id/technique/phase/agent_role/reviewer_id."""

    @patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"})
    @patch("src.fagan_tool.providers.openai_provider.OpenAI")
    def test_reviewer_call_writes_reviewer_id_phase_technique(self, mock_openai_class):
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        mock_client.chat.completions.create.return_value = _usage_response(
            "{}", prompt_tokens=5, completion_tokens=2, total_tokens=7
        )
        provider = OpenAIProvider(model="gpt-4o-mini")
        logger = UsageLogger(context={"run_id": "run_1"})
        provider.attach_usage_logger(logger, DEFAULT_COST_CONFIG)

        # So setzt der Prozess den Kontext beim Reviewer-Call:
        provider.set_call_context(
            phase="individual_inspection",
            reviewer_id="reviewer_3_ubr",
            technique="UBR",
        )
        provider.generate([{"role": "user", "content": "x"}])

        row = logger.rows[-1]
        assert row["run_id"] == "run_1"
        assert row["reviewer_id"] == "reviewer_3_ubr"
        assert row["phase"] == "individual_inspection"
        assert row["technique"] == "UBR"

    @patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"})
    @patch("src.fagan_tool.providers.openai_provider.OpenAI")
    def test_reviewer_id_does_not_leak_to_next_phase(self, mock_openai_class):
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        mock_client.chat.completions.create.return_value = _usage_response("{}")
        provider = OpenAIProvider(model="gpt-4o-mini")
        logger = UsageLogger(context={"run_id": "run_1", "technique": "UBR"})
        provider.attach_usage_logger(logger, DEFAULT_COST_CONFIG)

        # Reviewer-Call setzt reviewer_id ...
        provider.set_call_context(phase="individual_inspection", reviewer_id="reviewer_1_ubr")
        provider.generate([{"role": "user", "content": "a"}])
        # ... danach Meeting-Phase, reviewer_id zurückgesetzt
        provider.set_call_context(phase="inspection_meeting", reviewer_id="", technique="UBR")
        provider.generate([{"role": "user", "content": "b"}])

        assert logger.rows[0]["reviewer_id"] == "reviewer_1_ubr"
        assert logger.rows[1]["reviewer_id"] == ""  # kein Leak
        assert logger.rows[1]["phase"] == "inspection_meeting"

    @patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"})
    @patch("src.fagan_tool.providers.openai_provider.OpenAI")
    def test_agent_role_set_via_base_agent(self, mock_openai_class):
        from src.fagan_tool.agents.base_agent import BaseAgent

        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        mock_client.chat.completions.create.return_value = _usage_response("ok")
        provider = OpenAIProvider(model="gpt-4o-mini")
        logger = UsageLogger(context={"run_id": "run_1"})
        provider.attach_usage_logger(logger, DEFAULT_COST_CONFIG)

        agent = BaseAgent(provider, role="reviewer")
        agent.call_llm("hello")

        assert logger.rows[-1]["agent_role"] == "reviewer"

    def test_set_context_ignores_none_but_allows_empty_clear(self):
        logger = UsageLogger(context={"run_id": "r", "technique": "UBR"})
        logger.set_context(reviewer_id="rev_1")
        assert logger.context["reviewer_id"] == "rev_1"
        # None ignorieren (kein versehentliches Löschen)
        logger.set_context(reviewer_id=None)
        assert logger.context["reviewer_id"] == "rev_1"
        # Leerstring löscht bewusst
        logger.set_context(reviewer_id="")
        assert logger.context["reviewer_id"] == ""


class TestProcessContextWiring:
    """_set_usage_context am Prozess ist dry-run-sicher."""

    def _make_dry_process(self, tmp_path):
        from src.fagan_tool.core.process import FaganProcess
        from src.fagan_tool.core.schemas import (
            InspectionConfig, ConditionType, ReadingTechnique, LLMParams,
        )
        config = InspectionConfig(
            inspection_id="ctx_test",
            condition=ConditionType.C1_UBR,
            reading_techniques=[ReadingTechnique.UBR],
            artifacts=["design/test.pdf"],
            llm_params=LLMParams(model="gpt-4o-mini", provider="openai"),
            dry_run=True,
        )
        return FaganProcess(config, output_dir=tmp_path)

    def test_set_usage_context_noop_in_dry_run(self, tmp_path):
        process = self._make_dry_process(tmp_path)
        assert process.provider is None
        assert process.usage_logger is None
        # Darf nicht crashen, obwohl kein Provider/Logger existiert.
        process._set_usage_context(phase="planning", reviewer_id="")

    def test_dry_run_completes_and_writes_no_usage_log(self, tmp_path):
        process = self._make_dry_process(tmp_path)
        run = process.run()
        assert run is not None
        # Kein Usage-Log bei dry_run.
        assert not (process.output_dir / "llm_usage.csv").exists()


class TestEvaluationUntouched:
    def test_evaluation_module_imports_without_usage_dependency(self):
        # Sicherstellen, dass evaluation weiterhin unabhängig importierbar ist.
        import importlib
        mod = importlib.import_module("src.fagan_tool.evaluation")
        assert hasattr(mod, "DefectMatcher")
        assert hasattr(mod, "GoldLoader")
