"""Tests für das robuste .env-Laden im Costed-Runner.

Geprüft wird:
1. `.env` mit OPENAI_API_KEY wird geladen.
2. eine bereits gesetzte Environment-Variable wird NICHT überschrieben.
3. eine fehlende `.env` führt nicht zum Absturz.
4. der Key-Wert wird NICHT im Output ausgegeben.

Es werden keine echten LLM-Runs gestartet (subprocess wird gemockt).
"""

import importlib.util
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "run_costed_split_soft_n10.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("costed_runner_under_test", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


SECRET = "sk-test-DO-NOT-LOG-1234567890"


class TestEnvParsing:
    def test_parse_env_file_basic(self, tmp_path):
        mod = _load_module()
        env = tmp_path / ".env"
        env.write_text(
            "# Kommentar\n"
            "\n"
            'OPENAI_API_KEY="quoted-value"\n'
            "OTHER=plain\n"
            "export EXPORTED='single'\n",
            encoding="utf-8",
        )
        parsed = mod._parse_env_file(env)
        assert parsed["OPENAI_API_KEY"] == "quoted-value"
        assert parsed["OTHER"] == "plain"
        assert parsed["EXPORTED"] == "single"

    def test_load_env_sets_missing_key(self, tmp_path, monkeypatch):
        mod = _load_module()
        env = tmp_path / ".env"
        env.write_text(f"OPENAI_API_KEY={SECRET}\n", encoding="utf-8")
        monkeypatch.setattr(mod, "ENV_FILE", env)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        mod._load_env()
        assert mod.os.environ.get("OPENAI_API_KEY") == SECRET

    def test_load_env_does_not_override_existing(self, tmp_path, monkeypatch):
        mod = _load_module()
        env = tmp_path / ".env"
        env.write_text("OPENAI_API_KEY=from-dotenv\n", encoding="utf-8")
        monkeypatch.setattr(mod, "ENV_FILE", env)
        monkeypatch.setenv("OPENAI_API_KEY", "already-set")
        mod._load_env()
        assert mod.os.environ.get("OPENAI_API_KEY") == "already-set"

    def test_missing_env_file_no_crash(self, tmp_path, monkeypatch):
        mod = _load_module()
        monkeypatch.setattr(mod, "ENV_FILE", tmp_path / "does_not_exist.env")
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        # darf nicht crashen
        mod._load_env()
        assert mod.os.environ.get("OPENAI_API_KEY") is None


class TestNoSecretInOutput:
    def _temp_manifest(self, tmp_path):
        m = tmp_path / "manifest.csv"
        m.write_text(
            "dataset,run_id,technique,reviewers,config_path,command,status\n"
            "costed_split_soft_n10,costed_ubr_split_soft_n10_001,UBR,10,"
            "configs/experiments/costed_split_soft_n10_ubr.yaml,"
            "fagan run --config configs/experiments/costed_split_soft_n10_ubr.yaml "
            "--run-id costed_ubr_split_soft_n10_001,planned\n",
            encoding="utf-8",
        )
        return m

    def test_key_found_path_no_secret_logged(self, tmp_path, monkeypatch, capsys):
        mod = _load_module()
        # .env mit Secret, das geladen wird
        env = tmp_path / ".env"
        env.write_text(f"OPENAI_API_KEY={SECRET}\n", encoding="utf-8")
        monkeypatch.setattr(mod, "ENV_FILE", env)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        # Pfade auf temp umbiegen, reale Dateien/Runs nicht anfassen
        monkeypatch.setattr(mod, "MANIFEST", self._temp_manifest(tmp_path))
        monkeypatch.setattr(mod, "STATUS_OUT", tmp_path / "status.csv")
        monkeypatch.setattr(mod, "RUNS_DIR", tmp_path / "runs")
        # KEIN echter Run: subprocess.run mocken
        calls = {}

        class _Proc:
            returncode = 0

        def _fake_run(cmd, cwd=None):
            calls["cmd"] = cmd
            return _Proc()

        monkeypatch.setattr(mod.subprocess, "run", _fake_run)

        rc = mod.main()
        out = capsys.readouterr().out
        assert rc == 0
        # Key wurde gefunden und gemeldet, aber NICHT der Wert
        assert "OPENAI_API_KEY found: true" in out
        assert SECRET not in out
        # subprocess wurde (gemockt) aufgerufen -> Key-found-Pfad lief
        assert calls.get("cmd") is not None

    def test_no_key_path_lists_commands(self, tmp_path, monkeypatch, capsys):
        mod = _load_module()
        monkeypatch.setattr(mod, "ENV_FILE", tmp_path / "missing.env")
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.setattr(mod, "MANIFEST", self._temp_manifest(tmp_path))
        monkeypatch.setattr(mod, "STATUS_OUT", tmp_path / "status.csv")
        monkeypatch.setattr(mod, "RUNS_DIR", tmp_path / "runs")
        rc = mod.main()
        out = capsys.readouterr().out
        assert rc == 0
        assert "OPENAI_API_KEY found: false" in out
        assert "fagan run --config" in out  # geplante Befehle gelistet
