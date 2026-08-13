# Fagan Inspection Tool

Multi-Agenten-LLM-basiertes Software-Inspektionswerkzeug nach Fagan-Methodik. Entwickelt für eine Masterarbeit zur automatisierten Defekterkennung in Software-Design-Dokumenten mit Evaluation gegen einen Gold-Standard (36 Defekte). Unterstützt UBR (Usage-Based Reading), CBR (Checklist-Based Reading) und PBR (Perspective-Based Reading). PBR ist implementiert und wurde in 20 zusätzlichen Runs supplementär untersucht; es gehört nicht zum quantitativen UBR-vs-CBR-Hauptvergleich.

---

## Aktueller Projektstand (final)

- **Finaler Datensatz:** `costed_split_soft_n10` (40 Runs: 20 UBR + 20 CBR, n = 10).
- **Aktive Ergebnisse:** `results/costed_split_soft_n10/`.
- **Rohläufe:** `runs/costed_ubr_split_soft_n10_*`, `runs/costed_cbr_split_soft_n10_*` und `runs/costed_pbr_split_soft_n10_*`.
- **Finale Ergebnisdokumentation:** [`docs/FINAL_COSTED_EXPERIMENT_RESULTS.md`](docs/FINAL_COSTED_EXPERIMENT_RESULTS.md).
- **Instrumentierung:** Die Software protokolliert je Modellaufruf Tokens,
  Provider-Aufrufsdauer und technische API-Kosten. Jeder der insgesamt
  60 finalen Runs (40 Haupt-Runs + 20 supplementäre PBR-Runs) enthält dazu
  eine eigene `runs/<run_id>/llm_usage.csv`. Die Usage-/Kostenanalyse des
  CBR-/UBR-Hauptdatensatzes (40 Runs) liegt unter
  `results/costed_split_soft_n10/costs/`; die 20 PBR-Runs besitzen eine
  separate supplementäre Usage-/Kostenanalyse unter
  `results/costed_pbr_split_soft_n10/costs/`.
- **Reproduktion (finaler Ergebnisstand, zweistufig):**

  ```bash
  # 1. Automatische Auswertungen und Review-Kandidaten erzeugen
  python scripts/evaluate_costed_split_soft_n10.py

  # 2. Final festgelegte manuelle Bewertungsentscheidungen anwenden
  python scripts/apply_costed_manual_gold_match_decisions.py
  ```

  Schritt 1 erzeugt die automatischen Auswertungen unter
  `results/costed_split_soft_n10/` und schreibt das Review-Sheet
  `manual_gold_match/manual_gold_match_review_sheet.csv` neu; die Felder
  `human_decision` und `human_reason` sind danach zunächst leer.
  Schritt 2 trägt die final festgelegten 14 manuellen
  Bewertungsentscheidungen ein und erzeugt beziehungsweise aktualisiert
  `manual_gold_match/manual_gold_match_human_summary.csv`. Der
  vollständige finale manuelle Evidenzstand liegt erst nach beiden
  Schritten vor.
  Optional können anschließend die Kostenartefakte unter
  `results/costed_split_soft_n10/costs/` neu erzeugt werden
  (`python scripts/costed_split_soft_n10_cost_per_gold_tp.py` und
  `python scripts/personnel_cost_scenarios_costed_split_soft_n10.py`).
  `results/costed_split_soft_n10/final_costed_results_summary.json` ist eine
  kuratierte finale Referenzdatei und wird durch diese Schritte nicht
  verändert. Details siehe [`USAGE_EXAMPLES.md`](USAGE_EXAMPLES.md),
  Abschnitt „Reproduktion des finalen CBR-/UBR-Ergebnisstands".
- **Scope (finaler Hauptvergleich):** CBR und UBR bilden den quantitativen
  Hauptvergleich. **PBR** wurde in 20 zusätzlichen Runs supplementär untersucht
  und manuell validiert. Im untersuchten Setup ergaben sich dadurch keine
  zusätzlichen bestätigten Goldstandard-IDs gegenüber der bestätigten
  UBR-/CBR-Menge. PBR ist nicht Teil des quantitativen CBR-/UBR-Hauptvergleichs.
  Eine **hybride Lesetechnik** war nicht Gegenstand der Untersuchung und wurde
  nicht als eigene Run-Bedingung operationalisiert.
  **`UBR ∪ CBR`** ist nur eine nachträgliche Ergebnis-Union, keine hybride Technik.
- **PBR Supplementary Analysis:** Eine separate Zusatzanalyse liegt unter
  `results/costed_pbr_split_soft_n10/` und
  [`docs/PBR_SUPPLEMENTARY_MANUAL_VALIDATION_SUMMARY.md`](docs/PBR_SUPPLEMENTARY_MANUAL_VALIDATION_SUMMARY.md).
  Ergebnis: **keine zusätzlichen bestätigten PBR-only Gold-IDs gegenüber UBR/CBR**;
  **keine** Hybrid-Evaluation. Der Hauptvergleich bleibt unberührt.
  Post-hoc Union und Abgrenzung zur hybriden Lesetechnik: siehe
  [`docs/TECHNIQUE_COMBINATION_POST_HOC_UNION.md`](docs/TECHNIQUE_COMBINATION_POST_HOC_UNION.md).

> Hinweis: Die Abschnitte unten beschreiben teils den allgemeinen
> Werkzeug-Workflow (Dry-Run, Einzel-Runs). Für die finalen
> Ergebnisse gilt ausschließlich der costed-Datensatz oben.

---

## Voraussetzungen

- Python 3.11+
- Für Tests und `fagan dry-run` ist kein API-Key erforderlich
- Für echte OpenAI-Runs: `OPENAI_API_KEY` — wahlweise als Umgebungsvariable
  oder über eine `.env`-Datei nach Vorlage `.env.example`

---

## Quickstart

### 1. Projekt entpacken und venv erstellen

```bash
# Projekt-ZIP entpacken, dann in das Projektverzeichnis wechseln
cd Fagan_Code
python3 -m venv .venv
source .venv/bin/activate   # macOS/Linux
```

### 2. Dependencies installieren und Tests prüfen

```bash
python -m pip install -e ".[dev,plots]"
pytest -q
```

Erwartete Ausgabe: alle automatisierten Tests bestehen.

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

Hinweis: `dry-run` verwendet keine externe LLM-API. `ubr`, `cbr` und
`full` führen echte OpenAI-Aufrufe aus und benötigen einen gültigen
`OPENAI_API_KEY` (das Skript prüft den Key vor dem Start und bricht
andernfalls ab). Echte Inspektionsläufe erzeugen neue Run- und
Evaluationsartefakte unter `runs/<RUN_ID>/` und `eval/<RUN_ID>/`.

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

## Finale Experimentkonfigurationen

Die finalen Läufe (20 CBR + 20 UBR + supplementär 20 PBR, je n = 10,
split-soft) verwenden die Konfigurationen unter `configs/experiments/`:

```bash
set -a; source .env; set +a
RUN_ID="cbr_$(date +%Y%m%d_%H%M%S)"
fagan run --config configs/experiments/costed_split_soft_n10_cbr.yaml --run-id "$RUN_ID"
fagan eval --run "$RUN_ID" --gold artifacts/gold/Faults_List_In_ver6.xls --match-threshold 0.65
```

Analog: `costed_split_soft_n10_ubr.yaml` (UBR) und
`costed_pbr_split_soft_n10.yaml` (PBR, supplementär).

Das Ausführen einer Experimentkonfiguration erzeugt einen neuen Run. Die
60 finalen Runs sind bereits im Projekt enthalten und müssen zur Prüfung
des übergebenen Projektstands nicht erneut erzeugt werden. Für die
erneute Auswertung der vorhandenen finalen Runs ist der oben
dokumentierte zweistufige Reproduktionsablauf maßgeblich.

Requirements-PDF (`TextReqSpec_v3.6.pdf`) wird als Input-Artefakt geladen.

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
| `final_defects_gold_aligned.json` | Gefilterte Teilmenge der finalen Defekte für die optionale Auswertung mit `fagan eval --gold-aligned` |
| `llm_usage.csv` | Tokens, Aufrufdauer und technische API-Kosten je Modellaufruf |

Defekte enthalten neben `position`/`description`/`evidence` zusätzlich
`entity`, `expected`, `observed` und `evidence_location` (Inspection-Record-Qualität,
siehe [`docs/DEFECT_REPORT_QUALITY.md`](docs/DEFECT_REPORT_QUALITY.md));
fehlende Felder werden über `flags` (z. B. `missing_entity`) markiert,
ohne Defekte zu verwerfen.

### Nach `fagan eval` (`eval/<RUN_ID>/`)

| Datei | Inhalt |
|-------|--------|
| `metrics.json` | Precision, Recall, F1, Risiko-Breakdown |
| `matches.json` | Match-Details (found_id, gold_id, similarity) |
| `matches_enriched.csv` | Spreadsheet-freundliche Match-Tabelle |

### Finale Ergebnisdatensätze (`results/`)

Der finale Ergebnisbestand liegt unter `results/costed_split_soft_n10/`
(Hauptvergleich UBR vs. CBR) und `results/costed_pbr_split_soft_n10/`
(supplementäre PBR-Analyse); Details siehe `results/README.md`.

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
| `fagan verify` | Projektanforderungen prüfen |

`fagan verify` führt intern auch einen simulierten `fagan dry-run` aus.
Dieser verwendet keinen externen API-Aufruf und kann `runs/demo_dry_run/`
erzeugen oder aktualisieren.

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
python -m pip install -e ".[dev,plots]"
```

### "Gold file not found"

```bash
ls -la artifacts/gold/
# Erwartete Datei: Faults_List_In_ver6.xls
```

### Tests schlagen fehl

```bash
python -m pip install -e ".[dev,plots]"
pytest -v  # Verbose für Details
```

---

## Lesetechniken

### UBR (Usage-Based Reading)

- **Config:** `configs/examples/c1_ubr.yaml`
- **Fokus:** Use-Case-Szenarien, MSC-Diagramme
- **Artefakte:** Design PDF + Requirements PDF + UseCases PDF + UBR Guide

### CBR (Checklist-Based Reading)

- **Config:** `configs/examples/c1_cbr.yaml`
- **Fokus:** 7-Punkte-Checkliste (CL1-CL7)
- **Artefakte:** Design PDF + Requirements PDF + UseCases PDF + Checklist YAML

### PBR (Perspective-Based Reading)

> Scope: PBR wurde in 20 zusätzlichen Runs supplementär untersucht und manuell
> validiert. PBR ist **nicht** Teil des finalen quantitativen Hauptvergleichs
> (`costed_split_soft_n10`, UBR vs. CBR).

- **Config:** `configs/examples/c3_pbr_team.yaml`
- **Perspektiven:** Tester, Designer, User

---

## Projektstruktur

```
Fagan_Code/
├── artifacts/
│   ├── input/          # Eingabe-Dokumente (Design, UseCases, Guides)
│   └── gold/           # Gold-Standard (nur für Evaluation)
├── configs/
│   ├── examples/       # Beispiel-Inspektionen (c1_ubr.yaml, c1_cbr.yaml, ...)
│   └── experiments/    # Finale Experiment-Configs (costed_split_soft_n10_*.yaml)
├── prompts/            # Agent-Prompt-Templates
├── src/fagan_tool/     # Source Code
├── tests/              # Automatisierte Unit-Tests
├── docs/               # Methodik- und Ergebnisdokumentation
├── scripts/            # Run-/Auswertungs-Skripte (analyze_overlaps.py u. a.)
├── runs/               # 60 finale Inspektions-Runs (20 CBR, 20 UBR, 20 PBR)
├── eval/               # Evaluations-Ergebnisse (generiert bei fagan eval)
└── results/            # Finale Ergebnisdatensätze (costed_split_soft_n10, costed_pbr_split_soft_n10)
```

---

## Weiterführende Dokumentation

- [`docs/FINAL_COSTED_EXPERIMENT_RESULTS.md`](docs/FINAL_COSTED_EXPERIMENT_RESULTS.md) – **finale** kostenbezogene Ergebnisse (`costed_split_soft_n10`)
- [`ARCHITECTURE.md`](ARCHITECTURE.md) – System-Architektur
- [`docs/MATCHING_VALIDITY.md`](docs/MATCHING_VALIDITY.md) – Matching-Algorithmus
- [`docs/REQUIREMENTS_CHECKLIST.md`](docs/REQUIREMENTS_CHECKLIST.md) – Projektanforderungen (RA-R28)
- [`USAGE_EXAMPLES.md`](USAGE_EXAMPLES.md) – Ausführliche Nutzungs- und Reproduktionsanleitung

---

## Was dieses Projekt leistet

Dieses Tool bildet den klassischen Fagan-Inspektionsprozess mit LLM-Agenten nach:

1. **Moderator** plant die Inspektion und validiert die Ergebnisse
2. **Unabhängige Reviewer-Agenten** (konfigurierbare Anzahl, z. B. 3 in den Beispielkonfigurationen, 10 in den finalen Experimenten) inspizieren das Designdokument (UBR, CBR oder PBR)
3. **Scribe** konsolidiert die Ergebnisse und erzeugt eine finale Fehlerliste
4. **Evaluation** gleicht gefundene Fehler gegen den Gold-Standard ab (Precision, Recall, F1)
5. **Manuelle Validierung** ermöglicht CSV-Export für menschliche Überprüfung

---

## Manuelle Validierung

```bash
fagan manual-template --run <RUN_ID>    # CSV exportieren
# eval/<RUN_ID>/matches_manual.csv bearbeiten (TRUE/FALSE setzen)
fagan manual-eval --run <RUN_ID>        # Validierte Metriken berechnen
```

Ergebnis: `eval/<RUN_ID>/metrics_manual.json` mit manuell validierten
Referenzmetriken. Dieser generische Einzel-Run-Workflow ist von der finalen
manuellen Validierung des `costed_split_soft_n10`-Experiments getrennt
(siehe Reproduktionsablauf oben und `USAGE_EXAMPLES.md`).

---

## Lizenz

MIT License
