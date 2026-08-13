# Defect-Report-Qualität

## Warum

Bei `match-threshold = 0.65` (konservativ gewählt)
gehen Treffer verloren, sobald Reviewer-Defekte zu vage formuliert sind
oder die Lokationsangaben unvollständig bleiben. Klassische Fagan-Records
adressieren das mit einem festen Berichtsschema (Where? What is expected?
What was observed? Where is the evidence?).

Die Software hebt die **Output-Qualität** der Reviewer auf dieses
Niveau, **ohne** den Matcher, die Metriken oder den Goldstandard zu
beeinflussen:

- Der Matcher (`src/fagan_tool/evaluation/*`) bleibt davon unberührt.
- Der Goldstandard (`artifacts/gold/*`) bleibt davon unberührt.
- Die Qualitätsmaßnahmen liegen ausschließlich in (a) den Reviewer-Prompts
  (Disziplin / Format) und (b) optionalen Feldern des `Defect`-Schemas.

## Defect-Felder für die Berichtsqualität

| Feld                  | Pflicht?              | Beispiel                                   | Quelle                              |
| --------------------- | --------------------- | ------------------------------------------ | ----------------------------------- |
| `entity`              | wenn benannt vorhanden | `"Reject_Order"`                           | exakt aus Artefakt abgeschrieben    |
| `expected`            | empfohlen             | `"MSC must contain a Reject_Order arrow."` | hergeleitet aus Requirements / UC   |
| `observed`            | empfohlen             | `"Only Confirm arrow is present."`         | hergeleitet aus Design / MSC        |
| `evidence`            | bestehend (Dict)      | `{"quote_or_paraphrase": "…", …}`          | kurzer Auszug ≤ 25 Wörter           |
| `evidence_location`   | empfohlen             | `"p. 7, 3.4.1, MSC"`                       | exakt oder aus `page_hint+position` |

Die Felder `entity`, `expected`, `observed` und `evidence_location` sind
in `Defect` (Pydantic) `Optional[str]`. Die Felder `position`,
`page_hint`, `description` und `evidence` sind davon unabhängig im
Schema definiert.

## Validierungs-Flags

Die `Defect`-Validierung setzt (informational, nie rejecting):

- `missing_entity`
- `missing_expected`
- `missing_observed`
- `missing_evidence` — wenn `evidence.quote_or_paraphrase` leer ist
- `missing_evidence_location` — wenn weder ein expliziter Wert noch
  `page_hint`/`position` einen plausiblen Pointer ergibt

Sie landen alongside der bereits existierenden Flags
(`missing_position`, `missing_description`, `incomplete`) im
`flags`-Array jedes Defekts. So lässt sich pro Run / pro Reviewer sofort
sehen, wie viele Defekte unter dem Qualitätsstandard liegen, ohne dass
welche verworfen werden.

## Deterministische Komposition von `evidence_location`

Wenn das Feld leer ist, wird es im `Defect`-Validator zusammengesetzt
— rein formal, ohne neue Information:

| `page_hint` | `position`     | abgeleitetes `evidence_location` |
| ----------- | -------------- | -------------------------------- |
| `"p. 7"`    | `"3.4.1"`      | `"p. 7, 3.4.1"`                  |
| `"p. 7"`    | `""` / `"unknown"` | `"p. 7"`                     |
| `""`        | `"Table 1"`    | `"Table 1"`                      |
| `""`        | `"unknown"`    | leer → `missing_evidence_location` |

Das vermeidet, dass ein Reviewer "vergisst", den Pointer explizit
hinzuschreiben, ohne dass der Prozess eigene Schlussfolgerungen über das
Artefakt zieht.

## Prompts

`prompts/reviewer_{ubr,cbr,pbr_user,pbr_tester,pbr_designer}.txt`
enthalten jeweils:

1. ein JSON-Beispiel mit diesen Feldern + einer realistischen
   Lokationsangabe,
2. einen "Mandatory Fields"-Block, der jedes Feld nennt und
   sagt, ob es Pflicht ist,
3. eine **Anti-Hallucination-Regel**: `entity`,
   `evidence.quote_or_paraphrase` und `evidence_location` müssen aus dem
   Artefakt stammen — wer das nicht belegen kann, darf den Defekt nicht
   loggen.
4. einen Block **"STRICT INSPECTION RECORD FORMAT (HARD STOP)"** mit
   einer expliziten Hard-Requirement-Liste und der Do-not-log-Regel
   (siehe nächster Abschnitt).

Es wurden **keine Gold-Referenzen** in Prompts hinzugefügt.

## Hard requirement: defects without entity/expected/observed are not reported

Jeder Reviewer-Prompt enthält den Block **"STRICT INSPECTION RECORD
FORMAT (HARD STOP)"**. Dort steht in beiden Sprachen das gleiche
Verbot:

- Wenn `entity`, `expected` oder `observed` nicht aus den Artefakten
  belegbar sind, darf der Defekt **nicht** geloggt werden. Stille ist
  besser als ein schwacher Record ("Defekt nicht melden wenn
  entity/expected/observed nicht artefakt-belegbar sind.").
- Platzhalter-Werte wie `"unknown"`, `"n/a"`, `"tbd"`, `"UNK"` sind in
  allen Pflichtfeldern verboten.
- Verweise auf den Goldstandard oder die Fault-Liste sind verboten.

## record_quality_mode: warn vs repair

`extra_config.record_quality_mode` schaltet das Verhalten, wenn ein
Reviewer-Defekt `expected` oder `observed` leer lässt:

| Modus    | Zweite LLM-Anfrage? | Verhalten bei fehlendem `expected`/`observed`                                                                    |
| -------- | ------------------- | ---------------------------------------------------------------------------------------------------------------- |
| `warn`   | nein (Default)      | Defekt bleibt erhalten. Validator setzt nur `missing_expected` / `missing_observed`.    |
| `repair` | ja, genau **einmal**| Ein Repair-Call sammelt alle unvollständigen Defekte und bittet das Modell, `expected`/`observed` artefakt-belegt nachzutragen oder den Defekt **fallen zu lassen**. Defekte, die nach dem Repair-Call weiterhin Lücken haben, werden im Process gedroppt (Quality-Gate). |

Der Repair-Call sendet pro Defekt nur die nötigen Spalten zurück
(`id`, `position`, `page_hint`, `entity`, `evidence_location`,
`evidence.quote_or_paraphrase`, `description`) — keine Flags, kein
Originalkontext. Das hält den Token-Aufwand klein und vermeidet,
dass das Modell sein eigenes Urteil aus dem ersten Durchgang sieht.

`record_quality_mode: "repair"` ist in den
`configs/experiments/{ubr,cbr}_split_soft_n10.yaml` aktiviert (dort
ist die Anforderung an bewertbare Inspection Records am stärksten).
Der Default ist `warn`. Configs ohne explizite Angabe verwenden dieses
Standardverhalten.

Folgen für Token-Aufwand: maximal **1** zusätzliche LLM-Anfrage pro
Reviewer pro Run, und nur dann, wenn überhaupt ein Defekt
unvollständig ist. Bei sauberen Reviewer-Outputs entstehen keine
Mehrkosten.

### Safety Net: Repair darf niemals alles wegdroppen

Wenn der Repair-Call

- einen Parse-Fehler wirft,
- eine leere `defects`-Liste liefert, oder
- nur Defekte zurückgibt, die immer noch leere `expected`/`observed`
  haben,

dann **fällt** `repair` automatisch auf `warn`-Verhalten zurück: die
ursprünglichen Defekte bleiben erhalten. Damit produziert `repair` nie
ein 0-Defekt-Run, selbst wenn das Modell die Reparatur verweigert. Bei
**partieller** Reparatur (einige Defekte mit gefüllten Feldern, andere
nicht) wird **nicht** auf warn zurückgefallen — die reparierten Defekte
bleiben, die unrepairten fallen aus dem Output.

#### Fallback-Autofill: expected/observed deterministisch paraphrasiert

Im Fallback ersetzen wir die `missing_*`-Flags nicht stillschweigend, ABER
wir paraphrasieren expected/observed **deterministisch** aus dem
vorhandenen Defekttext — keine neuen Fakten:

- `observed` wird aus `evidence.quote_or_paraphrase` (bevorzugt) →
  `evidence`-String → `description` übernommen, jeweils verbatim und auf
  240 Zeichen begrenzt.
- `expected` wird **bevorzugt deterministisch aus `observed` abgeleitet**
  (symmetrischer Soll/Ist-Gegenpol, reines String-Rewrite ohne neue
  Fakten). Vier Regeln (case-insensitive, "specific first"):

  | Observed (Ist)                  | Expected (Soll)                |
  | ------------------------------- | ------------------------------- |
  | `... does not include X ...`    | `... should include X ...`     |
  | `... is not defined X ...`      | `... is defined X ...`         |
  | `... is missing X ...`          | `... is present/defined X ...` |
  | `... lacks X ...`               | `... has X ...`                |

  Trifft keine Regel zu, fällt der Autofill auf die generische
  Soll-Formel aus `entity` + `fault_type` zurück:
  `Expected: '<entity>' should be present/defined as specified.` (M),
  `... should match the specification/definition.` (W), sonst
  `... should satisfy the specification.`. `the described item` wird
  als Platzhalter eingesetzt, wenn `entity` leer ist.

Wo die Helper-Funktion gefüllt hat, werden `missing_expected` /
`missing_observed` aus den Flags entfernt und das Audit-Flag
`auto_expected_observed_from_text` einmalig ergänzt. So bleibt im Report
nachvollziehbar, welche Records vom Reviewer-LLM kamen und welche durch
den deterministischen Fallback befüllt wurden.

Wenn ein Defekt überhaupt keinen Text trägt (`entity`/`description`/
`evidence` alle leer), greift der Autofill **nicht** — die `missing_*`-
Flags bleiben dann ehrlich stehen.

### Repair-Prompt erlaubt Paraphrase aus den Defekt-Feldern

Der Repair-Prompt sagt dem Modell explizit, dass `expected`/`observed`
aus den **bereits gemeldeten** Feldern (`description`, `evidence`,
`entity`, `evidence_location`) paraphrasiert werden dürfen — das ist
keine Halluzination, sondern eine Soll/Ist-Reformulierung des eigenen
Reports. Beispiel im Prompt:

```
entity            = "Reject_Order"
description       = "'Reject_Order': A signal is missing ..."
evidence_location = "p. 7, 3.4.1, MSC"
=>
expected          = "Reject_Order should be present in the MSC at p. 7, 3.4.1."
observed          = "Reject_Order is missing from the MSC at p. 7, 3.4.1."
```

Das Modell soll nur dann einen Defekt weglassen, wenn selbst eine
solche Paraphrase aus dem Defekttext nicht möglich ist. So vermeiden
wir, dass der Repair-Schritt valide Reviewer-Findings nur deshalb
verwirft, weil die direkte Artefakt-Quelle für `expected`/`observed`
mehrdeutig ist.

## PBR description normalisation (opt-in, deterministic, no new facts)

PBR-Reviewer-Defekte verwenden häufig requirements-style Phrasen
("not specified", "expected behavior not specified", "incomplete"),
die gegen die design-/MSC-/API-Vokabular der Goldliste schlecht matchen
(beobachtete max_best_candidate_similarity ~0.45). Der
`_normalize_pbr_description`-Helper in
`src/fagan_tool/core/process.py` schreibt diese Phrasen
**deterministisch** in die Gold-Vokabular-Form um — ausschließlich auf
Basis des bereits gemeldeten Defekttexts. Es werden **keine neuen
Fakten** erfunden.

Quellpriorität für den umzuschreibenden Text:
`observed` > `evidence.quote_or_paraphrase` > `description`.

Substitutionsregeln (case-insensitive, in dieser Reihenfolge):

| Eingangsmuster                                                                              | Ergebnis                                       |
| ------------------------------------------------------------------------------------------- | ---------------------------------------------- |
| `expected behavior … (is) not specified`                                                    | `expected behavior is missing`                 |
| `timeout … (is) not specified / not defined`                                                | `timeout is missing`                           |
| `parameters … not fully defined / missing details`                                          | `parameter details are missing`                |
| `response format … (is) not specified`                                                      | `response format is missing`                   |
| `data structure … incomplete / missing field`                                               | `data structure is incomplete (missing fields)`|
| `no / missing acknowledgment / acknowledgement / feedback`                                  | `missing acknowledgment`                       |
| `is not specified / is not defined`                                                         | `is missing`                                   |
| `not specified / not defined`                                                               | `is missing`                                   |

Die normalisierte Description wird als
``'<entity>': <normalisierter Claim>.`` zurückgeschrieben (gekappt auf
200 Zeichen). Voraussetzungen für eine Umschreibung:

1. `technique` beginnt mit `"PBR"` (UBR/CBR werden nie angefasst).
2. `entity` ist gesetzt (sonst wird die Description unverändert
   gelassen — kein Anker).
3. Im Config-Block `extra_config.pbr_description_normalize` ist `true`
   (Default: `false`). In `configs/experiments/pbr_same_n10.yaml` ist
   der Flag bewusst aktiviert.

Wo umgeschrieben wurde, erscheint das Audit-Flag
`pbr_description_normalized` in `defect.flags`. Bei bereits gold-naher
Description bleibt alles unverändert und das Flag wird **nicht**
gesetzt.

## Entity fallback: deterministic extraction from description prefix

Wenn ein Reviewer das Pflichtfeld `entity` trotzdem leer lässt, greift
in `src/fagan_tool/core/process.py` ein **deterministischer Regex-Fallback**
(Funktion `_backfill_entity_from_description`):

- Beginnt die `description` mit einem gequoteten Token wie
  `"'Reject_Order': ..."` oder `'"Confirm_Voice": ...'`, wird der Inhalt
  dieses Tokens in `entity` übernommen und der `missing_entity`-Flag
  entfernt.
- Beginnt die `description` **nicht** mit einem gequoteten Token, bleibt
  `entity` `None` und der `missing_entity`-Flag erhalten — es wird
  nichts erfunden.
- `expected`, `observed` und `evidence_location` werden NIE im Code
  synthetisiert (außer der bestehenden rein formalen
  `evidence_location`-Komposition aus `page_hint`+`position`).

Aufgerufen wird der Fallback einmal pro Reviewer direkt nach
`reviewer.inspect(...)`; das Backfill-Ergebnis wird im Run-Log
ausgewiesen, damit sichtbar bleibt wie viele Defekte den Fallback nötig
hatten.

## Wirkung auf nachgelagerte Analyse

- Matcher / Metriken: `_get_evidence_text(evidence)` liest das
  dict-/string-Evidence-Feld. Die Felder `entity`, `expected`,
  `observed` und `evidence_location` sind für den Matcher nicht sichtbar.
- Reports (`final_defects.json`, `meeting_output.json`, `raw_defects_*.csv`):
  enthalten diese Felder. Konsumenten ignorieren unbekannte Schlüssel.
- `union_gold_coverage`, `fault_share_plots`, `gold_at_saturation`:
  benutzen `description / position / page_hint`. Bessere
  Reviewer-Outputs sollten die Treffer-Raten ohne weitere Änderungen
  *tendenziell* heben — garantiert ist das nicht.

## Begründung der Architektur-Entscheidungen

- **Warum `evidence` als Dict und nicht als String?** Der Matcher liest
  das Feld über `DefectMatcher._get_evidence_text(...)`, das sowohl Dict
  als auch String verarbeitet. Das geforderte kurze Quote deckt das Feld
  `quote_or_paraphrase` ab. Ein zusätzliches String-Feld würde Inhalte
  duplizieren, ohne Mehrwert für den Matcher.
- **Warum die Komposition im Schema (Validator) und nicht in
  `process.py`?** Damit greift sie für **jeden** Konstruktor-Aufruf von
  `Defect(...)` (Reviewer-Pfad, Scribe-Konsolidierung, Tests). Ein
  zentraler Punkt der Wahrheit reduziert Regressions-Risiko.
- **Warum keine Defekte verwerfen?** Die Flags dienen der
  Quality-Inspection, nicht der Rejection. So verwirft die Pipeline
  keine Defekte. Gleichzeitig lässt sich im Report die
  Qualitäts-Quote pro Run leicht ausrechnen
  (`#defects ohne missing_* / #defects`).
