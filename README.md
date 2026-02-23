# Fagan Inspection Tool

Multi-Agenten-LLM-basiertes Software-Inspektionswerkzeug nach Fagan-Methodik. Entwickelt für eine Masterarbeit zur automatisierten Defekterkennung in Software-Design-Dokumenten mit Evaluation gegen einen Gold-Standard (36 Defekte). Unterstützt UBR (Usage-Based Reading) und CBR (Checklist-Based Reading).

---

## Voraussetzungen

- Python 3.11+
- OpenAI API Key (für echte Runs, nicht für Dry-Run)
- `.env`-Datei mit API-Key (siehe `.env.example`)

---

## Quickstart

### 1. Repository klonen und venv erstellen

```bash
git clone <REPO_URL>
cd Fagan_Code
python3 -m venv .venv
source .venv/bin/activate   # macOS/Linux
```

### 2. Dependencies installieren und Tests prüfen

```bash
pip install -e .
pytest -q
```

Erwartete Ausgabe: `431 passed`

### 3. API-Key konfigurieren

```bash
cp .env.example .env
# .env editieren und OPENAI_API_KEY eintragen
```

### 4. Software starten

**Mit `run_example.sh` (empfohlen):**

| Modus | Befehl | Beschreibung |
|-------|--------|--------------|
| Dry-Run | `./run_example.sh dry-run` | Test ohne API-Key |
| UBR | `./run_example.sh ubr` | UBR-Inspektion + Evaluation |
| CBR | `./run_example.sh cbr` | CBR-Inspektion + Evaluation |
| Komplett | `./run_example.sh full` | UBR + CBR + Gold-Checksums |

---

## Manuelle Befehle (Alternative)

### Dry-Run (ohne API-Key)

```bash
fagan dry-run
```

Erzeugt: `runs/demo_dry_run/` mit simulierten Ergebnissen.

### UBR-Inspektion

```bash
set -a; source .env; set +a
RUN_ID="thesis_ubr_$(date +%Y%m%d_%H%M%S)"
fagan run --config configs/examples/c1_ubr.yaml --run-id "$RUN_ID"
fagan eval --run "$RUN_ID" --gold artifacts/gold/Faults_List_In_ver6.xls --match-threshold 0.65
```

### CBR-Inspektion

```bash
set -a; source .env; set +a
RUN_ID="thesis_cbr_$(date +%Y%m%d_%H%M%S)"
fagan run --config configs/examples/c1_cbr.yaml --run-id "$RUN_ID"
fagan eval --run "$RUN_ID" --gold artifacts/gold/Faults_List_In_ver6.xls --match-threshold 0.65
```

---

## Ergebnisorte

### Nach `fagan run` (`runs/<RUN_ID>/`)

| Datei | Inhalt |
|-------|--------|
| `config_snapshot.json` | Verwendete Konfiguration |
| `metadata.json` | Zeitstempel, Modell, Prompt-Versionen |
| `reviewer_outputs.json` | Defekte pro Reviewer |
| `meeting_output.json` | Konsolidierte Defekte + Duplikate |
| `final_defects.json` | Finale Defektliste |

### Nach `fagan eval` (`eval/<RUN_ID>/`)

| Datei | Inhalt |
|-------|--------|
| `metrics.json` | Precision, Recall, F1, Risiko-Breakdown |
| `matches.json` | Match-Details (found_id, gold_id, similarity) |
| `matches_enriched.csv` | Spreadsheet-freundliche Match-Tabelle |

---

## CLI-Übersicht

| Befehl | Zweck |
|--------|-------|
| `fagan run -c <config.yaml>` | Komplette Inspektion (Planning bis Follow-Up) |
| `fagan eval -r <run_id>` | Evaluation gegen Gold-Standard |
| `fagan dry-run` | Pipeline testen ohne API-Calls |
| `fagan report -r <run_id>` | Markdown-Report generieren |
| `fagan manual-template -r <run_id>` | CSV für manuelle Validierung exportieren |
| `fagan manual-eval -r <run_id>` | Metriken aus manueller Annotation berechnen |
| `fagan verify` | Alle Requirements prüfen (RA-R28) |

---

## Troubleshooting

### "OPENAI_API_KEY not set"

```bash
cp .env.example .env
# OPENAI_API_KEY eintragen
set -a; source .env; set +a
```

### "fagan: command not found"

```bash
pip install -e .
```

### "Gold file not found"

```bash
ls -la artifacts/gold/
# Erwartete Datei: Faults_List_In_ver6.xls
```

### Tests schlagen fehl

```bash
pip install -e .
pytest -v  # Verbose für Details
```

---

## Lesetechniken

### UBR (Usage-Based Reading)

- **Config:** `configs/examples/c1_ubr.yaml`
- **Fokus:** Use-Case-Szenarien, MSC-Diagramme
- **Artefakte:** Design PDF + UseCases PDF + UBR Guide

### CBR (Checklist-Based Reading)

- **Config:** `configs/examples/c1_cbr.yaml`
- **Fokus:** 7-Punkte-Checkliste (CL1-CL7)
- **Artefakte:** Design PDF + UseCases PDF + Checklist YAML

### PBR (Perspective-Based Reading)

- **Config:** `configs/examples/c3_pbr_team.yaml`
- **Perspektiven:** Tester, Designer, User

---

## Projektstruktur

```
Fagan_Code/
├── artifacts/
│   ├── input/          # Eingabe-Dokumente (Design, UseCases, Guides)
│   └── gold/           # Gold-Standard (nur für Evaluation)
├── configs/examples/   # Inspektions-Konfigurationen
│   ├── c1_ubr.yaml     # 3 UBR-Reviewer
│   ├── c1_cbr.yaml     # 3 CBR-Reviewer
│   └── ...
├── prompts/            # Agent-Prompt-Templates
├── src/fagan_tool/     # Source Code
├── tests/              # Unit Tests (431+)
├── docs/               # Dokumentation
├── scripts/local/      # Lokale Hilfsskripte
├── runs/               # Inspektions-Ergebnisse (generiert)
└── eval/               # Evaluations-Ergebnisse (generiert)
```

---

## Weiterführende Dokumentation

- [`ARCHITECTURE.md`](ARCHITECTURE.md) – System-Architektur
- [`docs/MATCHING_VALIDITY.md`](docs/MATCHING_VALIDITY.md) – Matching-Algorithmus
- [`docs/REQUIREMENTS_CHECKLIST.md`](docs/REQUIREMENTS_CHECKLIST.md) – Thesis-Anforderungen (RA-R28)
- [`USAGE_EXAMPLES.md`](USAGE_EXAMPLES.md) – Erweiterte Beispiele

---

## Was dieses Projekt leistet

Dieses Tool bildet den klassischen Fagan-Inspektionsprozess mit LLM-Agenten nach:

1. **Moderator** plant die Inspektion und validiert die Ergebnisse
2. **3 unabhängige Reviewer-Agenten** inspizieren das Designdokument (UBR oder CBR)
3. **Scribe** konsolidiert die Ergebnisse und erzeugt eine finale Fehlerliste
4. **Evaluation** gleicht gefundene Fehler gegen den Gold-Standard ab (Precision, Recall, F1)
5. **Manuelle Validierung** ermöglicht CSV-Export für menschliche Überprüfung

---

## Manuelle Validierung (für Thesis-Reporting)

```bash
fagan manual-template --run <RUN_ID>    # CSV exportieren
# eval/<RUN_ID>/matches_manual.csv bearbeiten (TRUE/FALSE setzen)
fagan manual-eval --run <RUN_ID>        # Validierte Metriken berechnen
```

Ergebnis: `eval/<RUN_ID>/metrics_manual.json` als autoritative Metrik-Quelle.

---

## Lizenz

MIT License
