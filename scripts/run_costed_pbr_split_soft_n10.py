#!/usr/bin/env python3
"""Führt die PBR-Zusatzanalyse ``costed_pbr_split_soft_n10`` aus.

SUPPLEMENTARY ANALYSIS — nicht Teil des UBR/CBR-Hauptvergleichs. Dies ist das
PBR-Pendant zu ``scripts/run_costed_split_soft_n10.py`` und verwendet denselben
Mechanismus: Es liest das Plan-Manifest
``results/costed_pbr_split_soft_n10_manifest.csv`` und startet die geplanten Runs
via ``fagan run --config <cfg> --run-id <rid>``. Pro Run wird echte
LLM-Tokenusage/Laufzeit nach ``runs/<run_id>/llm_usage.csv`` geloggt
(automatisch durch den Provider bei dry_run=false).

Sicherheitsregeln (identisch zum UBR/CBR-Runner):
- Das ursprüngliche Manifest wird NIE überschrieben. Der Status wird in eine
  separate Datei ``results/costed_pbr_split_soft_n10_manifest_status.csv``
  geschrieben.
- Bestehende ``runs/<run_id>`` werden NIE überschrieben -> Status
  ``skipped_exists``.
- Ohne ``OPENAI_API_KEY`` werden keine Runs gestartet; es werden nur die
  geplanten Befehle ausgegeben (Status ``planned_no_api_key``).
- Es werden KEINE UBR-/CBR-Manifeste, -Status oder -Runs berührt.

Goldstandard und Evaluation-Code werden nicht berührt.
"""

from __future__ import annotations

import csv
import os
import subprocess
from pathlib import Path
from typing import Dict, List

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
MANIFEST = _PROJECT_ROOT / "results" / "costed_pbr_split_soft_n10_manifest.csv"
STATUS_OUT = _PROJECT_ROOT / "results" / "costed_pbr_split_soft_n10_manifest_status.csv"
RUNS_DIR = _PROJECT_ROOT / "runs"
ENV_FILE = _PROJECT_ROOT / ".env"

STATUS_COLS = [
    "dataset", "run_id", "technique", "reviewers", "config_path", "command",
    "status", "usage_file_exists",
]


def _parse_env_file(path: Path) -> Dict[str, str]:
    """Minimaler ``.env``-Parser (Fallback ohne python-dotenv).

    Liest nur ``KEY=VALUE``-Zeilen, ignoriert Kommentare/Leerzeilen,
    entfernt umschließende Quotes. Gibt KEINE Werte aus.
    """
    out: Dict[str, str] = {}
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return out
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.lower().startswith("export "):
            line = line[len("export "):].strip()
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            out[key] = value
    return out


def _load_env() -> None:
    """Lädt ``.env`` aus dem Projektroot vor der Key-Prüfung.

    Nutzt das Projekt-Mechanismus (python-dotenv) und fällt auf einen
    minimalen Parser zurück. Bestehende, nicht-leere Environment-Variablen
    werden NICHT überschrieben. Es werden KEINE Werte geloggt.
    """
    if not ENV_FILE.exists():
        return
    try:
        from dotenv import load_dotenv  # Projekt-Mechanismus (siehe cli.py)
        # override=False: vorhandene Env-Variablen behalten Vorrang.
        load_dotenv(ENV_FILE, override=False)
    except Exception:
        # Fallback: minimaler Parser, ohne vorhandene Variablen zu überschreiben.
        for key, value in _parse_env_file(ENV_FILE).items():
            if not os.environ.get(key):  # nur setzen, wenn fehlend/leer
                os.environ[key] = value


def _load_manifest() -> List[Dict[str, str]]:
    if not MANIFEST.exists():
        raise SystemExit(f"[costed_pbr_run] Manifest fehlt: {MANIFEST}")
    with MANIFEST.open("r", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _write_status(rows: List[Dict[str, str]]) -> None:
    STATUS_OUT.parent.mkdir(parents=True, exist_ok=True)
    with STATUS_OUT.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=STATUS_COLS)
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in STATUS_COLS})


def main() -> int:
    rows = _load_manifest()
    _load_env()  # .env laden, BEVOR auf den Key geprüft wird
    have_key = bool(os.environ.get("OPENAI_API_KEY"))
    # Nur melden, ob ein Key gefunden wurde — niemals den Wert ausgeben.
    print(f"[costed_pbr_run] OPENAI_API_KEY found: {str(have_key).lower()}")

    if not have_key:
        print("[costed_pbr_run] OPENAI_API_KEY nicht gesetzt -> es werden KEINE Runs gestartet.")
        print("[costed_pbr_run] Geplante Befehle:")

    status_rows: List[Dict[str, str]] = []
    started = skipped = planned = failed = 0

    for r in rows:
        run_id = r["run_id"]
        cmd = r["command"]
        out = dict(r)
        out["usage_file_exists"] = ""

        if (r.get("status") or "").strip() != "planned":
            out["status"] = r.get("status", "")
            status_rows.append(out)
            continue

        run_dir = RUNS_DIR / run_id
        if run_dir.exists():
            out["status"] = "skipped_exists"
            skipped += 1
            print(f"[costed_pbr_run] SKIP (existiert): {run_id}")
            status_rows.append(out)
            continue

        if not have_key:
            out["status"] = "planned_no_api_key"
            planned += 1
            print(f"  {cmd}")
            status_rows.append(out)
            continue

        print(f"[costed_pbr_run] START: {run_id}")
        try:
            proc = subprocess.run(cmd.split(), cwd=str(_PROJECT_ROOT))
            ok = proc.returncode == 0
        except Exception as exc:  # pragma: no cover - Laufzeitschutz
            print(f"[costed_pbr_run] Fehler bei {run_id}: {exc}")
            ok = False

        usage_file = run_dir / "llm_usage.csv"
        out["usage_file_exists"] = "true" if usage_file.exists() else "false"
        if ok and usage_file.exists():
            out["status"] = "completed"
            started += 1
        elif ok and not usage_file.exists():
            out["status"] = "completed_no_usage_log"
            started += 1
        else:
            out["status"] = "failed"
            failed += 1
        status_rows.append(out)

    _write_status(status_rows)
    print(f"[costed_pbr_run] gestartet={started}, skipped_exists={skipped}, "
          f"planned_no_api_key={planned}, failed={failed}")
    print(f"[costed_pbr_run] Status -> {STATUS_OUT} (Original-Manifest unverändert)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
