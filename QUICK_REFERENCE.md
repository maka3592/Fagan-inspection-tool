# Schnellreferenz

## Installation

```bash
cd Fagan_Code
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev,plots]"
```

```bash
# API-Key nur für echte OpenAI-Runs (nicht für Tests oder Dry-Run):
cp .env.example .env   # anschließend OPENAI_API_KEY eintragen
# oder direkt als Umgebungsvariable:
export OPENAI_API_KEY="your-key"
```

## Befehle

### Inspektion ausführen
```bash
fagan run --config configs/examples/c1_ubr.yaml
```

### Ergebnisse auswerten (Threshold der Hauptauswertung: 0.65)
```bash
fagan eval --run c1_ubr_run_001 --gold artifacts/gold/Faults_List_In_ver6.xls --match-threshold 0.65
```

### Report erzeugen
```bash
fagan report --run c1_ubr_run_001
```

### Test ohne API (Dry-Run)
```bash
fagan dry-run
```

### Projektanforderungen verifizieren
```bash
fagan verify
```

### Manuelle Validierung (Vorlage + Metriken)
```bash
fagan manual-template --run c1_ubr_run_001   # CSV für manuelle Annotation exportieren
fagan manual-eval --run c1_ubr_run_001       # Metriken aus manueller Annotation berechnen
```

## Dateiablage

### Eingaben
- Design-Dokumente: `artifacts/input/design/`
- Use Cases: `artifacts/input/usecases/`
- Requirements: `artifacts/input/requirements/`
- UBR-Guides: `artifacts/input/guides/`
- Checklisten: `artifacts/input/checklists/`
- Goldstandard: `artifacts/gold/`
- Configs: `configs/examples/` und `configs/experiments/`

### Ausgaben
- Run-Ergebnisse: `runs/<inspection_id>/`
- Evaluation: `eval/<inspection_id>/`

## Konfigurationsvorlage

```yaml
inspection_id: "my_run_001"
condition: "C1_UBR"  # C1_UBR, C2_CBR, C3_PBR_TEAM

reading_techniques:
  - "UBR"  # UBR, CBR, PBR_TESTER, PBR_DESIGNER, PBR_USER

artifacts:
  - "design/my_design.pdf"
  - "requirements/my_requirements.pdf"
  - "usecases/my_usecases.pdf"

llm_params:
  provider: "openai"  # openai oder anthropic
  model: "gpt-4o-mini"
  temperature: 0.2
  max_tokens: 4096

dry_run: false
```

## Experimentelle Bedingungen

| Code | Name | Beschreibung |
|------|------|--------------|
| C1 | UBR | 3 unabhängige Reviewer, Use-Case-basierte Inspektion |
| C2 | CBR | 1 Reviewer, domänenspezifische Checkliste |
| C3 | PBR-Team | 3 Reviewer (Tester, Designer, User) |

PBR wurde supplementär untersucht und ist nicht Teil des quantitativen
UBR-vs-CBR-Hauptvergleichs.

## Defect Schema

```json
{
  "id": "meeting_7bfb1548",
  "position": "3.4.1",
  "page_hint": "p. 5",
  "risk": "A",
  "fault_type": "M",
  "description": "'Confirm': A signal is missing for confirming the order from the central to the taxi.",
  "evidence": {
    "quote_or_paraphrase": "The design does not specify a confirmation signal for the order sent to the taxi (p. 5)",
    "page_hint": "p. 5"
  },
  "confidence": 0.85,
  "flags": ["missing_entity", "missing_expected", "missing_observed"],
  "reviewer_id": null,
  "technique": null,
  "source_defect_ids": ["reviewer_1_ubr_e988706d", "reviewer_2_ubr_02f85891", "reviewer_3_ubr_88c0e1b8"],
  "source_reviewer_ids": ["reviewer_1_ubr", "reviewer_2_ubr", "reviewer_3_ubr"],
  "source_techniques": ["UBR"],
  "position_canonical": "3.4.1",
  "position_autofixed": false,
  "entity": null,
  "expected": null,
  "observed": null,
  "evidence_location": "p. 5, 3.4.1"
}
```

- `risk`: A (hoch), B (mittel), C (niedrig), UNK (unbekannt)
- `fault_type`: M (Missing), W (Wrong), UNK (unbekannt)
- `confidence`: 0.0–1.0
- `evidence` ist ein Objekt; die optionalen Qualitätsfelder `entity`,
  `expected` und `observed` können `null` sein.
- Bei konsolidierten Meeting-Defekten sind `reviewer_id` und `technique`
  `null`; die Herkunft steht in den Provenance-Feldern (`source_*`).
  Die Arrays sind hier gekürzt; das vollständige reale Beispiel steht in
  `USAGE_EXAMPLES.md`.

## Metrikausgabe

`fagan eval` schreibt `eval/<run_id>/metrics.json`. Gekürzte Auswahl der
im aktuellen `EvaluationMetrics`-Schema vorgesehenen Schlüssel (Werte
illustrativ; die Datei entsteht erst durch `fagan eval`):

```json
{
  "run_id": "c1_ubr_run_001",
  "total_found": 25,
  "total_gold": 36,
  "true_positives": 12,
  "true_positives_exact": 5,
  "true_positives_partial": 7,
  "false_positives": 13,
  "false_negatives": 24,
  "precision": 0.48,
  "recall": 0.333,
  "f1_score": 0.393,
  "recall_by_risk": {
    "A": 0.4,
    "B": 0.3,
    "C": 0.25,
    "UNK": 0.0
  },
  "match_threshold": 0.65
}
```

## Häufige Aufgaben

### Gefundene Defekte anzeigen
```bash
cat runs/<run_id>/final_defects.json | jq
```

### Metriken anzeigen
```bash
cat eval/<run_id>/metrics.json | jq
```

### Meeting-Protokoll anzeigen
```bash
cat runs/<run_id>/meeting_output.json | jq '.minutes'
```

### Vorhandene Runs auflisten
```bash
ls -l runs/
```

## Schnellstart mit Beispielskript

```bash
./run_example.sh dry-run   # Test ohne API-Key (keine externe LLM-API)
./run_example.sh ubr       # UBR-Run + Evaluation
./run_example.sh cbr       # CBR-Run + Evaluation
./run_example.sh full      # Kompletter Durchlauf (UBR + CBR + Gold-Checksums)
```

`ubr`, `cbr` und `full` führen echte OpenAI-Aufrufe aus und benötigen
einen gültigen `OPENAI_API_KEY`. Diese Modi erzeugen neue Run- und
Evaluationsartefakte unter `runs/<RUN_ID>/` und `eval/<RUN_ID>/`.

### Manueller Lauf

```bash
# .env laden — eine Möglichkeit, OPENAI_API_KEY bereitzustellen
# (alternativ den Key direkt als Umgebungsvariable exportieren)
set -a; source .env; set +a

# Inspektion starten (Modell laut Config: gpt-4o-mini)
RUN_ID="ubr_$(date +%Y%m%d_%H%M%S)"
fagan run --config configs/examples/c1_ubr.yaml --run-id "$RUN_ID"

# Auswerten
fagan eval --run "$RUN_ID" --gold artifacts/gold/Faults_List_In_ver6.xls --match-threshold 0.65
```

**Hinweis für zsh-Nutzer:** Befehle mit `#`-Kommentaren nicht direkt in
die interaktive Shell einfügen. Alternativ das Skript
`./run_example.sh` verwenden.

---

## Modell und strukturierte Ausgabe

Die finalen Experimente verwenden `gpt-4o-mini` mit `temperature: 0.2`
und `max_tokens: 4096` (siehe `configs/experiments/`).

Unterstützte Provider: `openai` und `anthropic` (Auswahl über
`llm_params.provider` in der Config).

Der OpenAI-Provider verwendet API-seitig durchgängig
`max_completion_tokens`. Bei Modellen, die keine eigenen
Sampling-Parameter unterstützen (z. B. eigene `temperature`-Werte),
werden diese Parameter automatisch weggelassen und eine Warnung
protokolliert.

### Strukturierte JSON-Ausgabe

- Reviewer- und Scribe-Agenten erzwingen die Ausgabe über
  `response_format` mit striktem JSON-Schema (`type: "json_schema"`).
- Leere oder abgeschnittene Antworten lösen genau einen automatischen
  Retry aus; bei abgeschnittenen Antworten mit verdoppeltem Tokenlimit.
- Fehlgeschlagene Reviewer-Ausgaben werden in `reviewer_outputs.json`
  als `is_incomplete: true` markiert.

## Troubleshooting

| Problem | Lösung |
|---------|--------|
| API-Key-Fehler | `OPENAI_API_KEY` setzen (bzw. `ANTHROPIC_API_KEY` für den Anthropic-Provider) |
| max_tokens-Fehler | Einige Modelle verwenden `max_completion_tokens` (wird automatisch behandelt) |
| temperature-Fehler | Einige Modelle unterstützen keine eigene `temperature` (wird automatisch ignoriert, mit Warnung) |
| Artefakt nicht gefunden | Pfad in der Config prüfen; Datei muss unter `artifacts/input/` existieren |
| Importfehler | `python -m pip install -e ".[dev,plots]"` ausführen |
| Tests schlagen fehl | Python-Version prüfen (3.11+ erforderlich) |
| JSON-Parse-Fehler | Rohantworten unter `runs/<run_id>/debug/` prüfen |

## Debugging von JSON-Parse-Fehlern

Liefert das LLM ungültiges JSON, werden Debug-Dateien automatisch
gespeichert:

```bash
# Ablageort der Debug-Dateien
ls runs/<run_id>/debug/

# Eine nicht parsebare Rohantwort ansehen
cat runs/<run_id>/debug/raw_response_reviewer_*.txt
```

Aufgetretene Parse-Fehler werden zusätzlich in `meeting_output.json`
unter `json_parse_errors` vermerkt (der Schlüssel existiert nur, wenn
Fehler aufgetreten sind):

```bash
cat runs/<run_id>/meeting_output.json | jq '.json_parse_errors'
```

## Tests

```bash
# Alle Tests ausführen
pytest tests/

# Einzelne Testdatei ausführen
pytest tests/test_matcher.py

# Mit Coverage (pytest-cov ist Teil der ".[dev]"-Extras)
pytest --cov=src/fagan_tool tests/
```

## Wichtige Nutzungsregeln

1. Den Goldstandard (`artifacts/gold/`) niemals als Inspektionsinput
   unter `artifacts/input/` ablegen
2. Setup zuerst mit `fagan dry-run` testen (ohne API-Aufrufe)
3. Jeder Run enthält einen Config-Snapshot (`config_snapshot.json`)
   zur Reproduzierbarkeit

## Hilfe

```bash
# Allgemeine Hilfe
fagan --help

# Hilfe zu einzelnen Befehlen
fagan run --help
fagan eval --help
fagan report --help
```

## Dokumentation

- `README.md` – zentrale Projekt- und Nutzungsdokumentation
- `ARCHITECTURE.md` – technische Architektur
- `USAGE_EXAMPLES.md` – ausführliche Nutzungs- und Reproduktionsanleitung
- `PROJECT_STRUCTURE.md` – Projektstruktur
