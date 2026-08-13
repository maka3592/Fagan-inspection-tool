# LLM-Usage- und Kostenlogging

## Zweck

Die Software protokolliert jeden realen Modellaufruf. Erfasst werden
Tokenusage, technische Laufzeit, Modell- und Aufrufkontext sowie
listenpreisbasierte Kosten. Alle 60 finalen Runs (20 CBR, 20 UBR und 20
supplementäre PBR-Runs) enthalten die per-Run-Datei
`runs/<run_id>/llm_usage.csv` mit realer API-Usage. Diese Daten bilden
die technische Grundlage der finalen Kostenanalyse.

Das Logging verändert weder den Matcher noch die Evaluation noch den
Goldstandard. Es ist nur aktiv, wenn ein `UsageLogger` an den Provider
angehängt ist, was bei echten (nicht-`dry_run`-) Runs automatisch
geschieht.

## Welche Felder geloggt werden

Pro LLM-Call wird eine Zeile mit folgenden Feldern erfasst
(`src/fagan_tool/utils/usage_logging.py`, `USAGE_FIELDS`):

| Feld | Bedeutung |
|---|---|
| `run_id` | Run-Bezeichner |
| `technique` | Reading-Technik des Runs (z. B. UBR, CBR) |
| `phase` | Inspektionsphase (sofern verfügbar, sonst leer) |
| `agent_role` | Rolle des aufrufenden Agents (z. B. reviewer, scribe, moderator) |
| `reviewer_id` | Reviewer-ID (sofern verfügbar, sonst leer) |
| `call_id` | eindeutige ID des Calls |
| `model` | verwendetes Modell |
| `start_time_utc` / `end_time_utc` | Zeitstempel (UTC) des Calls |
| `duration_seconds` | technische Laufzeit des API-Calls |
| `input_tokens` / `output_tokens` / `total_tokens` | echte API-Usage-Tokens |
| `input_cost` / `output_cost` / `total_cost` | berechnete Kosten (Annahme-Preise) |
| `usage_available` | `true`, wenn echte Usage-Zahlen vorlagen, sonst `false` |
| `error` | Fehlertext, falls der Call fehlschlug (sonst leer) |

### Wie die Kontextfelder gesetzt werden

Der Kontext wird über `provider.set_call_context(...)` an den
`UsageLogger` weitergereicht (No-op, wenn kein Logger angehängt ist) und je
geloggter Zeile ergänzt. Pro Call übergebene Werte haben Vorrang.

| Feld | Wo/wie gesetzt |
|---|---|
| `run_id` | beim Run-Start in `FaganProcess._init_usage_logger()` (run-weit) |
| `technique` | run-weit beim Start. Bei Reviewer-Calls exakt die Technik des Reviewers, danach (Meeting/Follow-Up) auf das run-weite Label zurückgesetzt |
| `phase` | bei Eintritt in jede Prozessphase via `_set_usage_context(phase=...)`: `planning`, `kickoff`, `individual_inspection`, `inspection_meeting`, `followup` |
| `agent_role` | in `BaseAgent.call_llm()` vor jedem Call (`self.role`) |
| `reviewer_id` | im Reviewer-Loop von `_conduct_individual_inspections()` als stabile, run-lokal eindeutige ID `reviewer_<i+1>_<technique>` |

**Reviewer-Calls müssen eine `reviewer_id` haben.** Sie wird unmittelbar
vor dem Reviewer-Aufruf gesetzt. Beim Verlassen der Reviewer-Phase wird
`reviewer_id` bewusst auf leer zurückgesetzt, damit sie **nicht** auf
Meeting-/Follow-Up-Calls leakt. Die ID ist deterministisch (kein Zufall),
reproduzierbar und innerhalb eines Runs eindeutig.

`reviewer_id` ist nur bei Reviewer-Calls gefüllt. Bei Nicht-Reviewer-Calls
(Moderator/Scribe in planning/kickoff/meeting/followup) ist sie leer. Die
Rolle steht dann in `agent_role`.

## Unterschied: technische Laufzeit vs. menschlicher Effort

`duration_seconds` misst die **Maschinenzeit** eines LLM-API-Calls (Latenz
des Modells/Netzes). Das ist **kein** menschlicher Inspektionsaufwand und
darf nicht als Effort-Proxy für eine Personalkostenrechnung verwendet
werden. Personalkosten werden getrennt und szenariobasiert behandelt.

## Preise sind dokumentierte Annahmen

Die Kostenberechnung nutzt `configs/llm_costs.yaml`:

```yaml
model_name: gpt-4o-mini
currency: USD
input_price_per_1m_tokens: 0.15
output_price_per_1m_tokens: 0.60
```

Diese Preise sind die für die Untersuchung verwendeten, dokumentierten
Preisannahmen (Listenpreise, in der Konfigurationsdatei mit Prüfdatum
vermerkt) und nicht hardcodiert. Berechnung:
`cost = (tokens / 1_000_000) * price_per_1m_tokens`. Fehlen echte
Tokenzahlen (`usage_available = false`), werden **keine** Kosten erfunden.
Die Kostenfelder bleiben dann leer.

## Speicherorte

- Pro Run: `runs/<run_id>/llm_usage.csv` (in allen 60 finalen Runs vorhanden)
- Finale Aggregationen: `results/costed_split_soft_n10/costs/`
  (`usage_by_run.csv`, `usage_by_technique.csv`,
  `cost_per_gold_tp_summary.csv` u. a.)
- Ein globaler Log (`results/llm_usage_log.csv`) kann bei Läufen
  technisch entstehen, gehört aber nicht zum finalen Ergebnisbestand.
  Die finalen Usage-Auswertungen stammen aus den per-Run-Dateien.

Geschrieben wird nur, wenn echte LLM-Calls stattgefunden haben. `dry_run`
erzeugt keine Usage-Logs.

## Namenskonvention: Prefix `costed_`

Die für die Kostenanalyse verwendeten finalen Runs tragen den
Run-Prefix `costed_` (z. B. `costed_ubr_split_soft_n10_001`). Der Prefix
kennzeichnet Runs mit gemessener Tokenusage als Kosten-Datengrundlage.

## Abgrenzung

- **Gemessene Tokenkosten**: aus real geloggten `input_tokens` /
  `output_tokens` × dokumentierten Preisen. Grundlage der finalen
  Kostenauswertung unter `results/costed_split_soft_n10/costs/`.
- **Geschätzte Tokenkosten**: aus Annahmen über Tokenmengen. Solche
  Schätzungen müssen ausdrücklich als Schätzung gekennzeichnet werden.

Dieses Dokument beschreibt den Logging-Mechanismus. Die darauf
aufbauende Kostenauswertung liegt unter
`results/costed_split_soft_n10/costs/` und ist in
`docs/FINAL_COSTED_EXPERIMENT_RESULTS.md` zusammengefasst.
