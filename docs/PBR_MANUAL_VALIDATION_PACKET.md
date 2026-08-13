# PBR Manual Validation Packet

## Purpose

- PBR-Kandidaten aus der **automatischen** Evaluation (kanonischer Matcher) werden
  hier für die **manuelle** Prüfung aufbereitet.
- Die **Felder der finalen manuellen Entscheidung wurden manuell gesetzt**
  (siehe je Abschnitt). Die **Suggested-assessment**-Abschnitte
  dokumentieren die vorbereitende Einschätzung.
- Ziel: prüfen, ob PBR **tatsächlichen Zusatznutzen** gegenüber UBR/CBR liefert
  (insbesondere bei neuen IDs `7, 9, 32, 38`).
- Quellen: `results/costed_pbr_split_soft_n10/pbr_match_candidates.csv`,
  `artifacts/gold/Faults_List_In_ver6.xls` (GoldLoader),
  UBR/CBR-Referenzentscheidungen aus
  `scripts/apply_costed_manual_gold_match_decisions.py`.

## Validation Rules

- **confirmed:** PBR-Defekt beschreibt **denselben inhaltlichen Fehler** wie der
  Goldstandard, nicht nur denselben Signal-/Use-Case-Namen.
- **doubtful:** teilweise passend, aber unklar, zu allgemein oder andere
  Fehlerursache.
- **rejected:** nur oberflächliche Ähnlichkeit, anderer Defekt, falsche Ursache,
  falscher Ort oder zu unspezifisch.
- Similarity-Score allein genügt **nicht**. Signalname allein genügt **nicht**.
- Für **neue IDs gegenüber UBR/CBR** besonders streng prüfen.

## Candidate Summary

| Gold-ID | Severity | Threshold(s) | Candidate type | n runs hitting | Best similarity | Existing UBR/CBR status | Priority | Manual decision |
|---|---|---|---|---:|---:|---|---|---|
| 7 | B | 0,60 | new-vs-UBR-CBR | 2 | 0.6226 | doubtful (UBR/CBR, t=0,60) | 1 | doubtful |
| 9 | C | 0,60 | new-vs-UBR-CBR | 1 | 0.6086 | keine UBR/CBR-Referenzentscheidung vorhanden | 1 | rejected |
| 32 | C | 0,60 | new-vs-UBR-CBR | 1 | 0.6019 | rejected (UBR/CBR) | 1 | rejected |
| 38 | C | 0,60 | new-vs-UBR-CBR | 6 | 0.6186 | rejected (UBR/CBR) | 1 | rejected |
| 8 | A | 0,65; 0,60 | existing-vs-UBR-CBR | 4 (t0,65) / 11 (t0,60) | 0.6708 | confirmed (UBR/CBR) | 2 | confirmed |
| 28 | C | 0,60 | existing-vs-UBR-CBR | 1 | 0.6026 | confirmed (UBR/CBR) | 2 | doubtful |

> Hinweis: 8 und 28 sind bereits in der bestätigten UBR/CBR-Menge; selbst bei
> PBR-`confirmed` ergeben sie **keine** zusätzliche Coverage. Die Zusatznutzen-
> Frage betrifft nur die neuen IDs 7, 9, 32, 38 — keine davon wurde `confirmed`.

## Candidate Detail Sections

### Gold-ID 7 — Severity B

#### Goldstandard
- Description: „Allocate car. Requirement 3.2.4 and the design of allocate_car
  (3.3.1 i STLDD) do not correspond."
- Expected entity/signal: `allocate_car` (Zuweisungslogik)
- Location: 3.3.1, 3.3.2
- Mechanismus: **Inkonsistenz** zwischen Requirement 3.2.4 und Design (W/wrong).

#### PBR Candidate
- PBR defect text: „'Allocate_car': The parameter types for Allocate_car are is
  missing in the design (p. 4)."
- Source run: …_001 · Reviewer/role: reviewer_2 (PBR_TESTER)
- Similarity score: 0.6226 · Threshold: 0,60 · n runs hitting: 2

#### Comparison
- same entity/signal? partial (beide `allocate_car`)
- same defect mechanism? no (Gold = Req/Design-Mismatch; PBR = fehlende Parametertypen)
- same location? partial (PBR p.4 vs Gold 3.3.1/3.3.2)
- sufficient specificity? partial
- likely same as gold? partial/no

#### UBR/CBR-Vergleichskontext
- t=0,60 **doubtful**: „Gleiche Entität und kompatible Location, aber nicht
  eindeutig derselbe Defekt" (LLM beschrieb fehlendes Bestätigungssignal). Die
  PBR-Meldung weicht erneut ab (fehlende Parametertypen).

#### Suggested assessment
- suggested: doubtful · rationale: gleiche Entität, abweichender Mechanismus ·
  confidence: low

#### Final manual decision
- final manual decision: **doubtful**
- reviewer notes: Gleiche Entität `allocate_car`, aber anderer Fehlermechanismus
  (Gold = Inkonsistenz Requirement 3.2.4 vs Design; PBR = fehlende Parametertypen);
  nicht eindeutig derselbe Defekt.

---

### Gold-ID 9 — Severity C

#### Goldstandard
- Description: „Message to a group of cars. It is not possible to send a message
  to a specific car group. A message has to be sent either to one or to all cars.
  Requirement 3.2.5."
- Expected entity/signal: Gruppen-Nachricht an Fahrzeuge
- Location: 3.3.1, 3.4.1
- Mechanismus: **fehlende Funktion** (M/missing) — keine Gruppen-Adressierung.

#### PBR Candidate
- PBR defect text: „'Allocate_car': The first parameter corresponds to the number
  on a operator. The second parameter corresponds to a taxi number (p. 4)."
- Source run: …_009 · Reviewer/role: reviewer_10 (PBR_DESIGNER)
- Similarity score: 0.6086 · Threshold: 0,60 · n runs hitting: 1

#### Comparison
- same entity/signal? no (PBR = `Allocate_car`-Parameter; Gold = Gruppen-Nachricht)
- same defect mechanism? no
- same location? partial
- sufficient specificity? no
- likely same as gold? no

#### UBR/CBR-Vergleichskontext
- keine UBR/CBR-Referenzentscheidung vorhanden (ID 9 war in UBR/CBR kein automatischer Match).

#### Suggested assessment
- suggested: rejected · rationale: andere Entität/anderer Fehler ·
  confidence: medium-high

#### Final manual decision
- final manual decision: **rejected**
- reviewer notes: PBR-Kandidat behandelt `Allocate_car`-Parameter; der
  Goldstandard behandelt die fehlende Gruppen-Nachricht an Fahrzeuggruppen —
  andere Entität/anderer Defekt.

---

### Gold-ID 28 — Severity C

#### Goldstandard
- Description: „Voice message parameters. The signal 'Voice_Msg' is inconsistent
  according to the parameters. Sometimes 2 is used and sometimes 3 is used."
- Expected entity/signal: `Voice_Msg` (Parameter-Inkonsistenz)
- Location: 3.4.2, 4.2
- Mechanismus: **Wrong** — inkonsistente Parameteranzahl.

#### PBR Candidate
- PBR defect text: „'Voice_Msg': The MSC in 4.2 does not clarify conditions for
  terminating voice messages (p. 10)."
- Source run: …_006 · Reviewer/role: reviewer_8 (PBR_DESIGNER)
- Similarity score: 0.6026 · Threshold: 0,60 · n runs hitting: 1

#### Comparison
- same entity/signal? yes (`Voice_Msg`)
- same defect mechanism? no (Gold = Parameter-Inkonsistenz; PBR = unklare Abbruchbedingungen)
- same location? yes (4.2)
- sufficient specificity? partial
- likely same as gold? partial/no

#### UBR/CBR-Vergleichskontext
- t=0,65 & t=0,60 **confirmed** — mit **anderem** LLM-Text, der die
  Parameter-Inkonsistenz traf. Die hier vorliegende PBR-Meldung adressiert einen
  anderen Aspekt (Abbruchbedingungen).

#### Suggested assessment
- suggested: doubtful · rationale: gleiches Signal, anderer Aspekt ·
  confidence: medium

#### Final manual decision
- final manual decision: **doubtful**
- reviewer notes: Gleiches Signal `Voice_Msg` und passende Location, aber Gold =
  inkonsistente Parameteranzahl, PBR = unklare Bedingungen für Abbruch/
  Terminierung; nicht eindeutig derselbe Defekt. ID 28 ist bereits in der
  bestätigten UBR/CBR-Menge → kein Zusatznutzen.

---

### Gold-ID 32 — Severity C

#### Goldstandard
- Description: „Start Voice. The signal 'Start_voice' from driver should be
  'send_voice'."
- Expected entity/signal: `Start_voice` (Umbenennung zu `send_voice`)
- Location: 4.2
- Mechanismus: **Wrong** — falscher Signalname (Rename nötig).

#### PBR Candidate
- PBR defect text: „'Start_Voice': 'Start_Voice' does not include confirmation
  handling in the MSC (p. 10)."
- Source run: …_020 · Reviewer/role: reviewer_8 (PBR_DESIGNER)
- Similarity score: 0.6019 · Threshold: 0,60 · n runs hitting: 1

#### Comparison
- same entity/signal? yes (`Start_Voice`)
- same defect mechanism? no (Gold = Rename; PBR = fehlende Confirmation-Handling)
- same location? yes (4.2 / p.10)
- sufficient specificity? partial
- likely same as gold? no

#### UBR/CBR-Vergleichskontext
- t=0,65 & t=0,60 **rejected**: „Gleicher Signalname und gleiche Location, aber
  anderer Defekt" (Gold = Rename; LLM = unnötige Wiederholung).

#### Suggested assessment
- suggested: rejected · rationale: gleicher Name, anderer Defekt · confidence: high

#### Final manual decision
- final manual decision: **rejected**
- reviewer notes: Gleicher Signalname `Start_Voice`, aber Gold = falscher
  Signalname/Rename zu `send_voice`, PBR = fehlendes Confirmation-Handling —
  anderer Defekt.

---

### Gold-ID 38 — Severity C

#### Goldstandard
- Description: „Order. The first signal 'Order' should be OrderOper. Further, one
  parameter is missing."
- Expected entity/signal: `Order` (Rename zu `OrderOper` + fehlender Parameter)
- Location: 4.1
- Mechanismus: **Missing/Wrong** — Rename plus fehlender Parameter.

#### PBR Candidate
- PBR defect text: „'Ack': The MSC in section 4.1 is missing a clear
  acknowledgment for the 'Order' signal (p. 9)."
- Source run: …_001 · Reviewer/role: reviewer_8 (PBR_DESIGNER)
- Similarity score: 0.6186 · Threshold: 0,60 · n runs hitting: 6

#### Comparison
- same entity/signal? partial (erwähnt `Order`, Fokus auf `Ack`)
- same defect mechanism? no (Gold = Rename + fehlender Parameter; PBR = fehlendes Acknowledgment)
- same location? yes (4.1)
- sufficient specificity? partial
- likely same as gold? no

#### UBR/CBR-Vergleichskontext
- t=0,65 & t=0,60 **rejected**: „Gleicher allgemeiner Signalbegriff und gleiche
  Location, aber anderer Defekt" (Gold = Rename + Parameter; LLM = fehlendes
  Rejection-Signal).

#### Suggested assessment
- suggested: rejected · rationale: gleicher Bereich, anderer Defekt · confidence: high

#### Final manual decision
- final manual decision: **rejected**
- reviewer notes: Gold = `Order` sollte `OrderOper` sein plus fehlender Parameter;
  PBR = fehlendes/unklares Acknowledgment für Order. Gleicher Bereich, aber
  anderer Defekt.

---

### Gold-ID 8 — Severity A

#### Goldstandard
- Description: „Cancel order. The signal 'Cancel_Order' is missing. Requirement
  3.2.4 is not fulfilled. No message to the operator. Manuel dispatch and cancel
  order."
- Expected entity/signal: `Cancel_Order` (fehlend)
- Location: 3.2.1, 3.4.2, Table 1
- Mechanismus: **Missing** — Cancel-Order-Signal/Benachrichtigung fehlt.

#### PBR Candidate
- PBR defect text (t=0,65): „'Order_Cancel': The design is missing a mechanism for
  notifying the operator of order cancellations."
- PBR defect text (t=0,60): „'Order_Cancel': The design states that an order can
  be cancelled but is missing details on the process (p. 5)."
- Source run: …_019 (t0,65) / …_008 (t0,60) · Reviewer/role: PBR_USER / PBR_TESTER
- Similarity score: 0.6708 (t0,65) / 0.6593 (t0,60) · n runs hitting: 4 / 11

#### Comparison
- same entity/signal? yes/partial (`Order_Cancel` ≈ `Cancel_Order`)
- same defect mechanism? yes (fehlende Cancel-Order-Funktion/Operator-Benachrichtigung)
- same location? partial (PBR p.5; Gold 3.2.1/3.4.2/Table 1)
- sufficient specificity? yes (t0,65)
- likely same as gold? yes (t0,65); partial (t0,60-Text allgemeiner)

#### UBR/CBR-Vergleichskontext
- t=0,65 & t=0,60 **confirmed**: fehlendes `Cancel_Order`-Signal. PBR trifft
  denselben Kern.

#### Suggested assessment
- suggested: confirmed (t=0,65) · rationale: gleicher inhaltlicher Defekt ·
  confidence: high

#### Final manual decision
- final manual decision: **confirmed**
- reviewer notes: PBR trifft den Kern des Goldstandards (fehlende Cancel-Order-
  Funktion bzw. fehlende Operator-Benachrichtigung). **Hinweis:** ID 8 ist bereits
  in der bestätigten UBR/CBR-Menge → kein Zusatznutzen für die Coverage.

## Overall Outcome (manual)

Manuelle Entscheidungen: 8 = confirmed; 7, 28 = doubtful; 9, 32, 38 = rejected.
Die **neuen** PBR-Kandidaten (7, 9, 32, 38) wurden **nicht** confirmed; 8 und 28
sind bereits bestätigt und liefern keine zusätzliche Coverage. **Ergebnis: kein
zusätzlicher bestätigter Goldfehler durch PBR gegenüber UBR/CBR.**
