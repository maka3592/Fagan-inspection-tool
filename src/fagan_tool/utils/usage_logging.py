"""Minimales, robustes Logging echter LLM-Token-Usage und -Laufzeit je Call.

Die bisherigen finalen Runs enthalten keine API-Usage-Tokens (siehe
``docs/TOKEN_COST_DATA_AVAILABILITY.md``). Dieses Modul ergänzt für
**neue** Runs ein optionales, robustes Logging pro LLM-Call. Es verändert
weder den Matcher noch die Evaluation noch den Goldstandard und ist
standardmäßig inaktiv (der Provider loggt nur, wenn ein ``UsageLogger``
angehängt wurde).

Geloggte Felder pro Call (siehe ``USAGE_FIELDS``):
run_id, technique, phase, agent_role, reviewer_id, call_id, model,
start_time_utc, end_time_utc, duration_seconds, input_tokens,
output_tokens, total_tokens, input_cost, output_cost, total_cost,
usage_available, error.

Hinweis: ``duration_seconds`` ist technische Maschinenlaufzeit des
API-Calls, KEIN menschlicher Inspektionsaufwand.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:  # PyYAML ist im Projekt vorhanden; Fallback schadet aber nicht.
    import yaml
except Exception:  # pragma: no cover
    yaml = None


USAGE_FIELDS: List[str] = [
    "run_id",
    "technique",
    "phase",
    "agent_role",
    "reviewer_id",
    "call_id",
    "model",
    "start_time_utc",
    "end_time_utc",
    "duration_seconds",
    "input_tokens",
    "output_tokens",
    "total_tokens",
    "input_cost",
    "output_cost",
    "total_cost",
    "usage_available",
    "error",
]

# Felder, die aus dem (run-/agent-weiten) Kontext gefüllt werden dürfen.
CONTEXT_FIELDS = {"run_id", "technique", "phase", "agent_role", "reviewer_id"}

# Default-Preise als Annahme; siehe configs/llm_costs.yaml (muss vor
# finaler Abgabe mit aktuellen Anbieterpreisen abgeglichen werden).
DEFAULT_COST_CONFIG: Dict[str, Any] = {
    "model_name": "gpt-4o-mini",
    "currency": "EUR",
    "input_price_per_1m_tokens": 0.15,
    "output_price_per_1m_tokens": 0.60,
}


def load_cost_config(path: Optional[Path] = None) -> Dict[str, Any]:
    """Lädt die Preis-Config aus YAML; fällt auf Defaults zurück.

    Preise sind konfigurierbare Annahmen, kein Hardcoding: fehlt die Datei
    oder ein Feld, wird der dokumentierte Default verwendet.
    """
    cfg = dict(DEFAULT_COST_CONFIG)
    if path is None:
        return cfg
    p = Path(path)
    if not p.exists() or yaml is None:
        return cfg
    try:
        loaded = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        if isinstance(loaded, dict):
            for k in DEFAULT_COST_CONFIG:
                if k in loaded and loaded[k] is not None:
                    cfg[k] = loaded[k]
    except Exception:
        # Robust: bei jedem Lesefehler Defaults verwenden.
        return dict(DEFAULT_COST_CONFIG)
    return cfg


def _as_int(value: Any) -> Optional[int]:
    """Nur echte Ganzzahlen akzeptieren (MagicMock/None/Strings -> None)."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    return None


def extract_usage(response: Any) -> Tuple[Optional[int], Optional[int], Optional[int], bool]:
    """Extrahiert (input, output, total, usage_available) aus einer Response.

    Robust gegenüber fehlender oder nicht-numerischer Usage (z. B. Mocks):
    liefert ``usage_available=False`` ohne zu crashen.
    """
    usage = getattr(response, "usage", None)
    if usage is None:
        return None, None, None, False
    input_tokens = _as_int(getattr(usage, "prompt_tokens", None))
    output_tokens = _as_int(getattr(usage, "completion_tokens", None))
    total_tokens = _as_int(getattr(usage, "total_tokens", None))
    # Manche SDKs nennen es anders – defensiv ergänzen.
    if input_tokens is None:
        input_tokens = _as_int(getattr(usage, "input_tokens", None))
    if output_tokens is None:
        output_tokens = _as_int(getattr(usage, "output_tokens", None))

    if input_tokens is None and output_tokens is None and total_tokens is None:
        return None, None, None, False

    if total_tokens is None and (input_tokens is not None or output_tokens is not None):
        total_tokens = (input_tokens or 0) + (output_tokens or 0)

    return input_tokens, output_tokens, total_tokens, True


def compute_costs(
    input_tokens: Optional[int],
    output_tokens: Optional[int],
    cost_config: Optional[Dict[str, Any]] = None,
) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    """Berechnet (input_cost, output_cost, total_cost) aus Tokenzahlen.

    cost = (tokens / 1_000_000) * price_per_1m_tokens. Fehlen Tokenzahlen,
    werden ``None``-Kosten zurückgegeben (keine erfundenen Werte).
    """
    cfg = cost_config or DEFAULT_COST_CONFIG
    in_price = float(cfg.get("input_price_per_1m_tokens", 0.0) or 0.0)
    out_price = float(cfg.get("output_price_per_1m_tokens", 0.0) or 0.0)

    input_cost = None
    output_cost = None
    if input_tokens is not None:
        input_cost = round((input_tokens / 1_000_000.0) * in_price, 8)
    if output_tokens is not None:
        output_cost = round((output_tokens / 1_000_000.0) * out_price, 8)

    if input_cost is None and output_cost is None:
        return None, None, None
    total_cost = round((input_cost or 0.0) + (output_cost or 0.0), 8)
    return input_cost, output_cost, total_cost


class UsageLogger:
    """Sammelt Usage-Zeilen je LLM-Call und schreibt sie als CSV.

    Run-/Agent-weite Kontextfelder (run_id, technique, phase, agent_role,
    reviewer_id) werden über :meth:`set_context` gesetzt und je Zeile
    ergänzt; pro-Call übergebene Werte haben Vorrang.
    """

    def __init__(self, context: Optional[Dict[str, Any]] = None):
        self.context: Dict[str, Any] = {}
        if context:
            self.set_context(**context)
        self.rows: List[Dict[str, Any]] = []

    def set_context(self, **kwargs: Any) -> None:
        for key, value in kwargs.items():
            if key in CONTEXT_FIELDS and value is not None:
                self.context[key] = value

    def record(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Erfasst eine Call-Zeile (Kontext + übergebene Felder)."""
        row: Dict[str, Any] = {f: "" for f in USAGE_FIELDS}
        for field, value in self.context.items():
            if field in row and value is not None:
                row[field] = value
        for key, value in data.items():
            if key in row and value is not None:
                row[key] = value
        self.rows.append(row)
        return row

    def write_csv(self, path: Path, append: bool = False) -> None:
        """Schreibt die gesammelten Zeilen. ``append`` hängt an eine
        bestehende Datei an, ohne sie zu überschreiben/zu truncaten."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        file_exists = path.exists()
        mode = "a" if append else "w"
        write_header = (not append) or (not file_exists) or path.stat().st_size == 0
        with path.open(mode, newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=USAGE_FIELDS)
            if write_header:
                writer.writeheader()
            for row in self.rows:
                writer.writerow({f: row.get(f, "") for f in USAGE_FIELDS})
