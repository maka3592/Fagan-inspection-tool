# Nutzungsbeispiele

## Vollständiges Workflow-Beispiel

### Schritt 1: Setup

```bash
# Virtuelle Umgebung erstellen und aktivieren
python3 -m venv .venv
source .venv/bin/activate

# Anwendung, Testabhängigkeiten und Plot-Unterstützung installieren
python -m pip install -e ".[dev,plots]"
```

Dies installiert das Kommandozeilenwerkzeug `fagan` zusammen mit den
Testabhängigkeiten (`dev`) und der optionalen Plot-Unterstützung
(`plots`, nur für `scripts/fault_share_plots.py` erforderlich).
Erforderlich ist Python 3.11 oder neuer.

Setze den OpenAI-API-Key, der für echte (nicht-`dry-run`) Inspektionen
verwendet wird. Die CLI lädt eine `.env`-Datei automatisch; exportiere
daher entweder die Variable oder erstelle eine `.env`-Datei aus der
mitgelieferten Vorlage:

```bash
# Option A: Key für die aktuelle Shell exportieren
export OPENAI_API_KEY="your-api-key-here"

# Option B: .env-Datei erstellen (wird von der CLI automatisch geladen)
cp .env.example .env
# anschließend .env bearbeiten und OPENAI_API_KEY setzen
```

### Schritt 2: Test per Dry-Run

```bash
# Ohne API-Aufrufe ausführen, um das Setup zu prüfen
fagan dry-run
```

Erwartete Ausgabe (gekürzt; simulierte Werte variieren):
```
Running dry-run inspection...
Note: This mode generates simulated outputs without API calls

Phase 1: Planning … Phase 7: Follow-Up
(alle sieben Fagan-Phasen laufen mit simulierten Ausgaben)

✓ Dry-run completed!
Generated <n> simulated defects
Results: runs/demo_dry_run/
```

### Schritt 3: Eingabeartefakte

Die von den mitgelieferten Beispielkonfigurationen benötigten
Eingabeartefakte liegen bereits unter `artifacts/input/` im Projekt
(Designdokument, Anforderungsspezifikation, Use Cases, UBR-Guide und
CBR-Checkliste). Für die mitgelieferten Beispiele müssen **keine**
Dateien kopiert werden.

Kopieren ist nur nötig, wenn eigene Dokumente inspiziert werden sollen.
Lege sie in diesem Fall im passenden Unterverzeichnis ab und referenziere
sie in der Konfiguration:

```bash
# Optional — nur für eigene Dokumente (für die Beispiele nicht erforderlich)
cp your_design.pdf artifacts/input/design/
cp your_usecases.pdf artifacts/input/usecases/
cp your_requirements.pdf artifacts/input/requirements/
```

### Schritt 4: Echte Inspektion ausführen (C1: UBR)

```bash
fagan run --config configs/examples/c1_ubr.yaml
```

Das Beispiel `c1_ubr.yaml` konfiguriert drei unabhängige UBR-Reviewer
(`reading_techniques: ["UBR", "UBR", "UBR"]`) mit dem OpenAI-Modell
`gpt-4o-mini`. Der Lauf:
1. lädt Designdokument, Anforderungen, Use Cases und UBR-Guide
2. führt die UBR-basierte Inspektion mit den drei Reviewern durch
3. erzeugt Defektbefunde und konsolidiert sie in der Meeting-Phase
4. speichert die Ergebnisse unter `runs/c1_ubr_run_001/`

Eine echte Inspektion benötigt einen gültigen `OPENAI_API_KEY` (siehe
Schritt 1). Ohne API-Key stattdessen `fagan dry-run` verwenden.

### Schritt 5: Auswertung gegen den Goldstandard

Der Goldstandard liegt bereits unter
`artifacts/gold/Faults_List_In_ver6.xls`; für die mitgelieferten
Beispiele ist kein Kopieren nötig. Führe die Auswertung mit dem
Threshold der Hauptauswertung aus:

```bash
fagan eval \
  --run c1_ubr_run_001 \
  --gold artifacts/gold/Faults_List_In_ver6.xls \
  --match-threshold 0.65
```

Erwartete Ausgabe (Werte hängen vom Run ab):
```
Evaluating run: c1_ubr_run_001
Loading gold standard from artifacts/gold/Faults_List_In_ver6.xls
  Gold defects: 36
Matching defects...
Calculating metrics...

Evaluation Metrics:
  (Tabelle mit Total Found, Total Gold, True/False Positives,
   False Negatives, Duplicates, Precision, Recall, F1 Score)

Recall by Risk Level:
  (Tabelle mit Recall je Risikostufe A/B/C/UNK)

Results saved to eval/c1_ubr_run_001/
```

### Schritt 6: Report erzeugen

```bash
fagan report --run c1_ubr_run_001
```

Dies erzeugt `eval/c1_ubr_run_001/report.md` mit:
- zusammenfassenden Statistiken
- Performance-Metriken
- Aufschlüsselung nach Risikostufen
- Hinweisen zur Interpretation

## Verschiedene Bedingungen ausführen

### C2: Checklist-Based Reading

Das Beispiel `c2_cbr.yaml` konfiguriert einen einzelnen CBR-Reviewer
(`reading_techniques: ["CBR"]`), der die Artefakte gegen die
domänenspezifische Checkliste
(`artifacts/input/checklists/cbr_checklist_v2.yaml`) prüft.

```bash
fagan run --config configs/examples/c2_cbr.yaml
fagan eval \
  --run c2_cbr_run_001 \
  --gold artifacts/gold/Faults_List_In_ver6.xls \
  --match-threshold 0.65
fagan report --run c2_cbr_run_001
```

### C3: PBR-Team (3 Reviewer)

Das Beispiel `c3_pbr_team.yaml` konfiguriert drei PBR-Reviewer mit
komplementären Perspektiven (`PBR_TESTER`, `PBR_DESIGNER`, `PBR_USER`).
PBR ist implementiert und wurde als supplementäre Untersuchung
evaluiert. PBR ist nicht Teil des finalen quantitativen
UBR-vs-CBR-Hauptvergleichs.

```bash
fagan run --config configs/examples/c3_pbr_team.yaml
fagan eval \
  --run c3_pbr_team_run_001 \
  --gold artifacts/gold/Faults_List_In_ver6.xls \
  --match-threshold 0.65
fagan report --run c3_pbr_team_run_001
```

## Eigene Konfiguration

Erstelle eine eigene Konfigurationsdatei:

```yaml
# my_inspection.yaml
inspection_id: "my_custom_run_001"
condition: "C1_UBR"

reading_techniques:
  - "UBR"

artifacts:
  - "design/my_design.pdf"
  - "usecases/my_usecases.pdf"

llm_params:
  provider: "openai"
  model: "gpt-4o-mini"
  temperature: 0.2
  max_tokens: 4096

dry_run: false
```

Ausführen:

```bash
fagan run --config my_inspection.yaml
```

## Mehrere Runs für die Auswertung wiederholter Runs

```bash
# Dieselbe Konfiguration 5-mal für die Auswertung wiederholter Runs ausführen
for i in {1..5}; do
  # inspection_id in der Konfiguration anpassen oder sed verwenden
  sed "s/run_001/run_00$i/" configs/examples/c1_ubr.yaml > temp_config.yaml
  fagan run --config temp_config.yaml
done

# Alle Runs mit explizitem Threshold auswerten
for i in {1..5}; do
  fagan eval --run c1_ubr_run_00$i \
    --gold artifacts/gold/Faults_List_In_ver6.xls \
    --match-threshold 0.65
done

# Metriken über die Runs vergleichen
cat eval/c1_ubr_run_00*/metrics.json | jq '.recall'
```

## Ergebnisse einsehen

### Gefundene Defekte anzeigen

```bash
cat runs/c1_ubr_run_001/final_defects.json | jq '.[0]'
```

Beispielausgabe (ein konsolidierter Meeting-Defekt):
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
  "source_defect_ids": [
    "reviewer_1_ubr_e988706d",
    "reviewer_1_ubr_829153ec",
    "reviewer_2_ubr_02f85891",
    "reviewer_3_ubr_88c0e1b8",
    "reviewer_4_ubr_96f65e7d",
    "reviewer_4_ubr_4ca9f604",
    "reviewer_5_ubr_adcc6103",
    "reviewer_6_ubr_b540bda8",
    "reviewer_6_ubr_db4cf087",
    "reviewer_6_ubr_3b34b0cd",
    "reviewer_7_ubr_c42d5815",
    "reviewer_10_ubr_8cf0beff"
  ],
  "source_reviewer_ids": [
    "reviewer_10_ubr",
    "reviewer_1_ubr",
    "reviewer_2_ubr",
    "reviewer_3_ubr",
    "reviewer_4_ubr",
    "reviewer_5_ubr",
    "reviewer_6_ubr",
    "reviewer_7_ubr"
  ],
  "source_techniques": ["UBR"],
  "original_position": null,
  "position_canonical": "3.4.1",
  "position_mentions": [],
  "position_autofixed": false,
  "position_autofix_reason": "",
  "entity": null,
  "expected": null,
  "observed": null,
  "evidence_location": "p. 5, 3.4.1"
}
```

`evidence` ist ein Objekt (`quote_or_paraphrase` plus optionalem
`page_hint`). Die Qualitätsfelder des Inspektionsprotokolls `entity`,
`expected` und `observed` sind optional und können `null` sein. Bei
konsolidierten Meeting-Defekten können `reviewer_id` und `technique`
`null` sein; die Herkunft ist in den Provenance-Feldern
(`source_defect_ids`, `source_reviewer_ids`, `source_techniques`)
dokumentiert. Die Positionsfelder (`original_position`,
`position_canonical`, `position_mentions`, `position_autofixed`,
`position_autofix_reason`) halten fest, wie die Position für das
Matching kanonisiert wurde.

### Match-Details anzeigen

```bash
cat eval/c1_ubr_run_001/matches.json | jq '.[] | select(.match_type == "exact")'
```

Die `match_type`-Werte sind kleingeschrieben: `exact`, `partial`,
`duplicate`, `no_match_potential_new`, `no_match_false_positive`.

### Meeting-Protokoll anzeigen

```bash
cat runs/c1_ubr_run_001/meeting_output.json | jq '.minutes'
```

## Behebung häufiger Probleme

### Problem: Große PDFs

Für sehr große PDFs (>100 Seiten) kommen in Frage:

1. das Dokument aufteilen
2. max_tokens erhöhen
3. die Chunking-Strategie nutzen (im PDFExtractor implementiert)

### Problem: Schwache Matching-Ergebnisse

Bei geringer Matching-Qualität:

1. Positionsformatierung im Goldstandard prüfen
2. Matcher-Thresholds über `--match-threshold` anpassen
3. Normalisierungsregeln in `matcher.py` prüfen

## Threshold-Sensitivitätsanalyse

Der Parameter `--match-threshold` steuert, wie strikt das Matching ist:

```bash
# Finaler Threshold der Hauptauswertung
fagan eval --run my_run --match-threshold 0.65

# Sensitivitätsschwelle und technischer CLI-Default
fagan eval --run my_run --match-threshold 0.60
```

**Wirkung des Thresholds:**
- **Niedrigerer Threshold**: Ein niedrigerer Threshold akzeptiert mehr
  automatische Match-Kandidaten. Dies kann den Recall erhöhen; zugleich
  können zusätzliche fehlerhafte Zuordnungen auftreten und die Precision
  kann sinken.
- **Höherer Threshold**: Ein höherer Threshold akzeptiert weniger
  automatische Match-Kandidaten. Der Recall kann sinken, während die
  Precision steigen kann.

Automatische Matches sind algorithmische Match-Kandidaten und nicht
automatisch gleichbedeutend mit final manuell bestätigten
Goldstandard-Zuordnungen. Aus den untersuchten Thresholds wird kein
optimaler Threshold abgeleitet.

Dokumentiere für eine reproduzierbare Auswertung stets den verwendeten
Threshold:

```bash
# Lauf mit explizitem Threshold für Reproduzierbarkeit
fagan eval --run experiment_001 --match-threshold 0.65 --gold artifacts/gold/Faults_List_In_ver6.xls

# Der Threshold wird in metrics.json unter evaluation_metadata.matcher_thresholds gespeichert
```

**Aufschlüsselung automatischer Matches (Exact vs. Partial):**
- **Exact-Matches** (similarity >= 0.85): Matches oberhalb der
  Exact-Match-Ähnlichkeitsgrenze
- **Partial-Matches** (threshold <= similarity < 0.85): verwandte Defekte

Die Metrikausgabe enthält:
- `true_positives_exact`: Anzahl der Exact-Matches
- `true_positives_partial`: Anzahl der Partial-Matches
- `similarity_score_mean_tp`: mittlere Ähnlichkeit aller TPs
- `similarity_score_min_tp` / `similarity_score_max_tp`: Spannweite der TP-Ähnlichkeiten

## Best Practices

1. **Immer zuerst dry-run ausführen**, um das Setup zu prüfen
2. **Versionskontrolle** für Konfigurationen und Prompts verwenden
3. **Prompt-Änderungen** in prompt_versions dokumentieren
4. **Wiederholte Runs verwenden**, wenn die Variabilität über mehrere Runs analysiert wird
5. **Goldstandard getrennt halten** – niemals mit Eingabeartefakten mischen
6. **Meeting-Protokolle prüfen**, um Konsolidierungsentscheidungen nachzuvollziehen
7. **Bedingungen vergleichen**, um die Wirksamkeit der Techniken zu bewerten

## Erweiterte Nutzung

### Programmatischer Zugriff

```python
from pathlib import Path
from fagan_tool.core.process import FaganProcess
from fagan_tool.core.schemas import InspectionConfig, ConditionType, ReadingTechnique, LLMParams

# Create config programmatically
config = InspectionConfig(
    inspection_id="prog_run_001",
    condition=ConditionType.C1_UBR,
    reading_techniques=[ReadingTechnique.UBR],
    artifacts=["design/doc.pdf"],
    llm_params=LLMParams(
        provider="openai",
        model="gpt-4o-mini",
        temperature=0.2,
        max_tokens=4096,
    ),
    dry_run=False,
)

# Run inspection
process = FaganProcess(config)
run = process.run()

# Access results
print(f"Found {len(run.final_defects)} defects")
for defect in run.final_defects:
    print(f"- {defect.position}: {defect.description}")
```

### Eigene Checkliste

Bearbeite `configs/checklists/cbr_minimal.yaml` oder erstelle eine
eigene Checkliste:

```yaml
# my_checklist.yaml
checklist_version: "1.0"
description: "My custom checklist"

categories:
  - name: "Security"
    items:
      - "Are authentication mechanisms specified?"
      - "Is sensitive data encrypted?"
      - "Are access controls defined?"
```

Referenziere sie in der Konfiguration:

```yaml
extra_config:
  checklist_path: "configs/checklists/my_checklist.yaml"
```

## Verifikation der Anforderungen

Verifiziere die Projektanforderungen:

```bash
# Automatisierte Verifikation ausführen
fagan verify

# Oder das eigenständige Skript verwenden
python scripts/verify_requirements.py
```

Erwartete Ausgabe (gekürzt):
```
Requirements Verification Report
(Tabelle mit ID, Description, Status und Evidence je Anforderung)

Summary:
  PASS: <n>
  PARTIAL: <n>
  FAIL: <n>
  SKIP: <n>
```

`fagan verify` beendet sich mit Exit-Code 1, wenn eine Anforderung den
Status FAIL hat.

Die Verifikation führt intern auch den lokalen `fagan dry-run`-Check
aus. Dieser verwendet simulierte Daten ohne externen API-Aufruf und kann
`runs/demo_dry_run/` erzeugen oder aktualisieren.

Details zu den Anforderungen enthält `docs/REQUIREMENTS_CHECKLIST.md`.

## Manueller Validierungs-Workflow

Für eine zusätzliche manuelle Validierung automatischer Matches:

### Schritt 1: Manuelle Vorlage erstellen

```bash
# Nach der Auswertung eine manuelle Validierungsvorlage erstellen
fagan manual-template --run c1_ubr_run_001
```

Dies erzeugt `eval/c1_ubr_run_001/matches_manual.csv` mit:
- allen Spalten aus `matches_enriched.csv`
- der Spalte `manual_is_true_match` (Standard: FALSE)
- der Spalte `manual_notes` für Anmerkungen

### Schritt 2: Manuelle Durchsicht

1. `matches_manual.csv` in einem Tabellenkalkulationsprogramm öffnen
2. Jede Match-Zeile prüfen
3. `manual_is_true_match` auf `TRUE` setzen, wenn das Match korrekt ist
4. Bei Bedarf Anmerkungen in der Spalte `manual_notes` ergänzen
5. Datei speichern

### Schritt 3: Manuelle Metriken berechnen

```bash
fagan manual-eval --run c1_ubr_run_001
```

Erwartete Ausgabe:
```
Manual Validation Metrics: c1_ubr_run_001

┏━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━┓
┃ Metric                  ┃  Value ┃
┡━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━┩
│ Total Matches Reviewed  │     25 │
│ Manual True Positives   │     18 │
│ Manual False Positives  │      7 │
│ Total Gold              │     36 │
│ False Negatives         │     18 │
│ Precision               │  0.720 │
│ Recall                  │  0.500 │
│ F1 Score                │  0.590 │
└─────────────────────────┴────────┘

Metrics saved to: eval/c1_ubr_run_001/metrics_manual.json
```

### Vergleich

Damit liegen zwei Metrik-Sätze vor:
- `metrics.json` – automatisches Matching (algorithmisch)
- `metrics_manual.json` – manuell validierte Referenzmetriken

Dies ermöglicht:
- die Durchsicht automatischer Match-Zuordnungen
- den Vergleich automatischer und manuell validierter Metriken
- das Erkennen mehrdeutiger oder fehlerhafter automatischer Zuordnungen

Dieser generische Einzel-Run-Workflow ist von der finalen manuellen
Validierung des `costed_split_soft_n10`-Experiments getrennt. Für den
finalen CBR-/UBR-Ergebnisstand ist der unten dokumentierte
Reproduktions-Workflow zu verwenden.

## Reproduktion des finalen CBR-/UBR-Ergebnisstands

Die vollständige Reproduktion des finalen Ergebnisstands von
`costed_split_soft_n10` besteht aus zwei Schritten:

```bash
# 1. Automatische Auswertungen und Review-Kandidaten erzeugen
python scripts/evaluate_costed_split_soft_n10.py

# 2. Final festgelegte manuelle Bewertungsentscheidungen anwenden
python scripts/apply_costed_manual_gold_match_decisions.py
```

Schritt 1 erzeugt alle automatischen Auswertungen unter
`results/costed_split_soft_n10/` sowie das Review-Sheet
`manual_gold_match/manual_gold_match_review_sheet.csv`. Das erzeugte
Review-Sheet enthält zunächst leere Felder für `human_decision` und
`human_reason`.

Schritt 2 trägt die final festgelegten 14 manuellen
Bewertungsentscheidungen in das Review-Sheet ein und erzeugt
beziehungsweise aktualisiert
`manual_gold_match/manual_gold_match_human_summary.csv`. Der vollständige
finale manuelle Evidenzstand liegt erst nach beiden Schritten vor.

Bei einer vollständigen Neuberechnung können anschließend die
Kostenartefakte unter `results/costed_split_soft_n10/costs/` erneut
erzeugt werden:

```bash
# 3. Kostenartefakte neu erzeugen
python scripts/costed_split_soft_n10_cost_per_gold_tp.py
python scripts/personnel_cost_scenarios_costed_split_soft_n10.py
```

Hinweis: `results/costed_split_soft_n10/final_costed_results_summary.json`
ist eine kuratierte finale Referenzdatei. Sie wird nicht automatisch durch
den Wrapper erzeugt und bleibt bei den obigen Schritten unverändert.
