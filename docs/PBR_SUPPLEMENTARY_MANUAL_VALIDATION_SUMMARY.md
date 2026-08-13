# PBR Supplementary Manual Validation Summary

## Summary

- PBR wurde als **zusätzliche Lesetechnik** (Supplementary Analysis) im selben
  instrumentierten Setup wie UBR/CBR ausgeführt (20 Runs, n = 10, gpt-4o-mini,
  split-soft) und automatisch gegen den 36-Fehler-Goldstandard evaluiert.
- Die automatischen PBR-Kandidaten wurden **manuell validiert**.
- **Keine neuen bestätigten PBR-only Gold-IDs gegenüber der bestätigten
  UBR/CBR-Menge.**
- Der **Hauptvergleich bleibt UBR vs. CBR**; PBR bleibt Zusatzanalyse.

## Decisions

| Gold-ID | Severity | Candidate type | Automatic threshold(s) | Manual decision | Rationale | Additional confirmed vs UBR/CBR? |
|---|---|---|---|---|---|---|
| 8 | A | existing-vs-UBR-CBR | 0,65; 0,60 | confirmed | trifft fehlende Cancel-Order-/Operator-Benachrichtigung; bereits in UBR/CBR-Menge | no (bereits bestätigt) |
| 7 | B | new-vs-UBR-CBR | 0,60 | doubtful | gleiche Entität `allocate_car`, aber anderer Mechanismus (Req/Design-Inkonsistenz vs fehlende Parametertypen) | no |
| 28 | C | existing-vs-UBR-CBR | 0,60 | doubtful | gleiches Signal `Voice_Msg`, aber anderer Aspekt (Parameter-Inkonsistenz vs Abbruchbedingungen); bereits in UBR/CBR-Menge | no (bereits bestätigt) |
| 9 | C | new-vs-UBR-CBR | 0,60 | rejected | andere Entität/anderer Defekt (Gruppen-Nachricht vs Allocate_car-Parameter) | no |
| 32 | C | new-vs-UBR-CBR | 0,60 | rejected | gleicher Signalname, anderer Defekt (Rename Start_voice→send_voice vs fehlendes Confirmation-Handling) | no |
| 38 | C | new-vs-UBR-CBR | 0,60 | rejected | gleicher Bereich, anderer Defekt (Rename Order→OrderOper + Parameter vs fehlendes Ack) | no |

**Zusammenfassung:** confirmed = {8}; doubtful = {7, 28}; rejected = {9, 32, 38}.
Neue manuell bestätigte PBR-only Gold-IDs gegenüber UBR/CBR: **keine**.

## Impact on Technique Combination Question

- PBR wurde als zusätzliche Technik getestet.
- Bei t = 0,60 existierten **neue automatische** Kandidaten (`7, 9, 32, 38`).
- Nach **manueller Validierung** blieb **kein** zusätzlicher bestätigter
  Goldfehler gegenüber der UBR/CBR-Menge.
- Damit liefert PBR in diesem Setup **keinen belegten Zusatznutzen** für eine
  Technik-Kombination.
- Das beantwortet die Frage nach einer „guten Kombination" empirisch für dieses
  Setup: Eine gute Kombination müsste **zusätzliche bestätigte Defekte** liefern;
  PBR tat das hier nicht. `UBR ∪ CBR ∪ PBR` (confirmed) = `UBR ∪ CBR` (confirmed).

## Interpretation Boundaries

- **Supplementary Analysis**, nicht Hauptvergleich.
- Ein Modell (gpt-4o-mini), eine Aufgabe (Taxi-Design), begrenztes Setup.
- **Keine** Aussage, dass PBR generell wirkungslos ist.
- **Keine** hybride Lesetechnik evaluiert (Unionen sind post-hoc Merges).
- Automatische Kandidaten zeigen: niedrigere Thresholds (t = 0,60) erzeugen
  **mehr Kandidaten**, aber nicht automatisch mehr **bestätigte** Fehler.

## Thesis-ready Wording

Ergänzend zum Hauptvergleich (UBR vs. CBR) wurde Perspective-Based Reading (PBR)
als **Zusatzanalyse** im identischen instrumentierten Setup (20 Läufe, zehn
Reviewer je Lauf, gpt-4o-mini, geteilter Scope) ausgeführt und automatisch gegen
denselben Goldstandard ausgewertet. Die automatischen Treffer wurden mit
derselben Matching-Logik erzeugt und anschließend manuell inhaltlich
geprüft.

Beim Hauptthreshold ergaben sich keine neuen automatischen Kandidaten gegenüber
der bereits bestätigten UBR/CBR-Menge. Bei der niedrigeren Sensitivitätsschwelle
traten zusätzliche automatische Kandidaten auf, von denen jedoch nach manueller
Validierung **keiner** als inhaltlich derselbe Goldstandard-Defekt bestätigt
werden konnte. PBR lieferte damit im untersuchten Setup **keinen zusätzlichen
bestätigten Goldfehler** gegenüber UBR und CBR.

Dieses Ergebnis ist auf das vorliegende Setup (ein Modell, eine
Spezifikation, ein Prompt-Satz) begrenzt und sollte nicht als generelle
Wirkungslosigkeit von PBR gelesen werden. Eine Technik-Kombination ist nur dann
gerechtfertigt, wenn sie **zusätzliche bestätigte** Defekte liefert. Ein solcher
Nachweis gelang hier nicht. Eine eigenständige hybride Lesetechnik war nicht
Gegenstand der Untersuchung.
