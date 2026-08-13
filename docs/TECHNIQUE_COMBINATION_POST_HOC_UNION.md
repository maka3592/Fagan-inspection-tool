# Technique Combination: Post-hoc Union

## Purpose

- Diese Datei beschreibt, wie die **getrennt erzeugten Ergebnislisten** der
  Lesetechniken **nachträglich vereinigt** wurden (post-hoc Union) und wie
  diese Unions interpretiert werden.
- Zur methodischen Abgrenzung wird erläutert, warum eine post-hoc Union
  **nicht** mit einer eigenständigen hybriden Lesetechnik gleichzusetzen ist.
- Neutral formuliert, ohne interne Bezeichnungen.

## Definitions

### Post-hoc Union (nachträgliche Mengenvereinigung)

- Die Lesetechniken werden **getrennt** ausgeführt.
- **Danach** werden die Ergebnislisten vereinigt.
- Beispiele: `UBR ∪ CBR`, `UBR ∪ PBR`, `UBR ∪ CBR ∪ PBR`.
- Eine Union ist **keine** neue Lesetechnik, **kein** neuer Prompt und
  **keine eigenständige Run-Bedingung** — sie ändert die Inspektion selbst
  nicht, sondern nur die nachträgliche Mengenbildung.

### Hybrid Reading Technique

- Eine **eigenständige, vorab operationalisierte** Lesetechnik.
- Kombiniert Perspektiven **bereits während** der Inspektion.
- Bräuchte **eigene Prompts, eigene Runs, eigene Evaluation und manuelle
  Validierung**.
- Darf **nicht** mit einer post-hoc Union verwechselt werden.

## Evidence from This Project

| Technique combination | Type | Evidence source | Automatic candidates | Manual validation outcome | Additional confirmed Gold-IDs? | Interpretation |
|---|---|---|---|---|---|---|
| UBR ∪ CBR | post-hoc Union | `docs/FINAL_COSTED_EXPERIMENT_RESULTS.md` (Abschnitte 6, 9) | t=0,65 union = UBR-Menge; t=0,60 union = UBR-Menge | CBR ⊆ UBR (bestätigte IDs) | **no** (keine zusätzlichen bestätigten CBR-only IDs) | Union erhöht die bestätigte Coverage gegenüber UBR allein nicht |
| UBR ∪ CBR ∪ PBR | post-hoc Union mit Supplementary PBR | `docs/PBR_SUPPLEMENTARY_MANUAL_VALIDATION_SUMMARY.md`, `results/costed_pbr_split_soft_n10/pbr_final_summary.json` | PBR autom.: t=0,65 `8`; t=0,60 `7 8 9 28 32 38` | PBR confirmed `8` (bereits in UBR/CBR-Menge); 7,28 doubtful; 9,32,38 rejected | **no** (keine zusätzlichen bestätigten PBR-only IDs) | Union mit PBR erhöht die bestätigte Coverage nicht |

Eine eigenständige hybride Lesetechnik wurde **nicht** implementiert, nicht
ausgeführt und nicht evaluiert; sie hätte einen eigenen experimentellen Arm
mit eigenen Prompts, Konfigurationen, Runs, Auswertung und manueller
Validierung erfordert.

## Answer to the Combination Question

- Eine **gute Kombination müsste zusätzliche bestätigte Defekte** liefern.
- **Automatische Kandidaten allein reichen nicht** (sie überschätzen die
  Erkennung; entscheidend ist die manuelle Validierung).
- Im untersuchten Setup zeigten die geprüften **Merges keinen zusätzlichen
  bestätigten Goldfehler** gegenüber der bestehenden bestätigten Menge.
- Daher gibt es in diesem Setup **keine empirische Grundlage**, eine Kombination
  als wirksamer zu berichten.
- Eine **echte Hybrid-Technik wurde nicht evaluiert**, weil sie methodisch ein
  **eigener experimenteller Arm** wäre (eigene Prompts/Runs/Validierung).
- **Eine eigenständige hybride Lesetechnik war nicht Gegenstand der
  Untersuchung.**

## Cost Interpretation

- Niedrige Tokenkosten machen zusätzliche Varianten technisch/wirtschaftlich
  leichter testbar.
- Niedrige Kosten **ersetzen aber keine Evidenz**.
- Das Kostenargument ist nur relevant, **wenn zusätzlicher bestätigter Nutzen**
  entsteht.
- Da PBR **keinen** zusätzlichen bestätigten Goldfehler lieferte, entsteht hier
  **kein belegter Kosten-/Nutzen-Vorteil** durch Erweiterung.

## Thesis-ready Wording

In dieser Arbeit wird zwischen einem **post-hoc Merge** (getrennte Ausführung der
Lesetechniken mit anschließender Vereinigung der Ergebnislisten, z. B. UBR ∪ CBR
oder UBR ∪ CBR ∪ PBR) und einer **echten hybriden Lesetechnik** (einer
eigenständig operationalisierten Technik, die Perspektiven bereits während der
Inspektion kombiniert) unterschieden. Ein Merge ist keine neue Lesetechnik,
sondern lediglich eine nachträgliche Mengenbildung über bereits erzeugte
Resultate.

Die geprüften Merges wurden ausgewertet: `UBR ∪ CBR` liefert keine zusätzlichen
bestätigten Goldfehler gegenüber UBR allein, und auch die ergänzend untersuchte
Perspective-Based Reading (PBR, Supplementary Analysis mit anschließender
manueller Validierung) erbrachte keine zusätzlichen bestätigten Goldfehler
gegenüber der bereits bestätigten UBR/CBR-Menge. Eine Kombination ist nur dann
gerechtfertigt, wenn sie zusätzliche **bestätigte** Defekte liefert; ein solcher
Nachweis gelang im untersuchten Setup nicht.

Eine echte hybride Lesetechnik wurde **nicht** evaluiert, da sie einen eigenen
experimentellen Arm mit eigenen Prompts, Läufen und manueller Validierung
erfordern würde; sie war **nicht Gegenstand der Untersuchung**. Diese Befunde sind auf das
vorliegende Setup (ein Modell, eine Spezifikation, ein Prompt-Satz) begrenzt und
sind **keine** generelle Aussage, dass hybride Ansätze oder PBR wirkungslos
seien.
