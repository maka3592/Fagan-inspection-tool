# Manual Gold Match Validation: `costed_split_soft_n10`

## Geltungsbereich

Diese Dokumentation beschreibt die manuelle semantische Validierung der
automatischen Gold-Zuordnungen für den finalen Datensatz
`costed_split_soft_n10`. Der Goldstandard umfasst 36 Referenzdefekte.
Ausgewertet werden der Hauptthreshold t = 0,65 und die
Sensitivitätsschwelle t = 0,60.

Die dokumentierten Bewertungsentscheidungen liegen unter:

`results/costed_split_soft_n10/manual_gold_match/manual_gold_match_review_sheet.csv`

Die zusammengefassten Ergebnisse liegen unter:

`results/costed_split_soft_n10/manual_gold_match/manual_gold_match_human_summary.csv`

Für die Ergebnisbewertung gelten die final festgelegten manuellen
Bewertungsentscheidungen.

## Validierungsvorgehen

Das automatische Matching erzeugt mögliche Zuordnungskandidaten zwischen
LLM-Defektmeldungen und Goldstandard-Defekten. Die automatische Zuordnung
entscheidet nicht abschließend, ob ein Goldstandard-Defekt gefunden
wurde. Jeder Kandidat wird anhand der konkreten LLM-Meldung und des
zugeordneten Goldstandard-Defekts manuell semantisch geprüft. Maßgeblich
sind insbesondere die betroffene Position, die beschriebene Abweichung,
der fachliche Zusammenhang und die inhaltliche Identität des
beschriebenen Defekts. Reine Textähnlichkeit genügt nicht für eine
Bestätigung.

Für die manuelle Validierung gelten drei Kategorien:

- `confirmed`: Die LLM-Meldung beschreibt den zugeordneten
  Goldstandard-Defekt inhaltlich ausreichend genau.
- `doubtful`: Die Zuordnung ist möglich, aber nicht eindeutig genug
  bestätigt.
- `rejected`: Die automatische Zuordnung wird nach der semantischen
  Prüfung verworfen.

Nur `confirmed` zählt als bestätigter Goldstandard-Treffer. `doubtful`
und `rejected` werden nicht als Treffer berücksichtigt. Mehrere
bestätigte Meldungen zu derselben Goldstandard-ID erhöhen die Abdeckung
nicht. Jede unterschiedliche bestätigte Goldstandard-ID wird auf der
gepoolten Ebene einmal gezählt.

## Finale Bewertungsentscheidungen

| Threshold | Automatische Kandidaten (Gold-IDs) | confirmed | doubtful | rejected | Bestätigte Gold-IDs | Bestätigter Recall | Bestätigte Abdeckung |
|---:|---|---|---|---|---:|---:|---:|
| 0,65 | `8 28 31 32 38` | `8 28 31` | — | `32 38` | 3 von 36 | 0,0833 | 8,33 % |
| 0,60 | `6 7 8 25 27 28 31 32 38` | `8 25 27 28 31` | `7` | `6 32 38` | 5 von 36 | 0,1389 | 13,89 % |

## Begründung ausgewählter Entscheidungen

Die folgenden Begründungen sind dem dokumentierten Review-Sheet
entnommen und beziehen sich auf die finalen Bewertungsentscheidungen:

- **ID 8 (`confirmed`)**: Gleiches Signal und kompatible Location. Die
  LLM-Meldung beschreibt ausdrücklich das fehlende
  `Cancel_Order`-Signal zum Stornieren akzeptierter Aufträge.
- **ID 25 (`confirmed`, t = 0,60)**: Die LLM-Meldung beschreibt eine
  fehlende Definition von `Order_number` im Kontext von `order_struct`
  und trifft damit den fehlenden Parameter des Goldstandard-Defekts
  hinreichend genau.
- **ID 27 (`confirmed`, t = 0,60)**: Der Goldstandard nennt fehlende
  Parameter beim Signal *Logged In*. Die LLM-Meldung beschreibt konkret
  die fehlende *Driver Number* beim Login-Signal.
- **ID 28 (`confirmed`)**: Die LLM-Meldung beschreibt inkonsistente
  `Voice_Msg`-Parameter gegenüber den erwarteten Parametern in Table 1
  und trifft damit den Kern des Goldstandard-Defekts.
- **ID 31 (`confirmed`)**: Die LLM-Meldung beschreibt ausdrücklich das
  fehlende `Confirm_Voice`-Signal.
- **ID 7 (`doubtful`, t = 0,60)**: Gleiche Entität und kompatible
  Location, aber inhaltlich nicht eindeutig derselbe Defekt. Der
  Goldstandard betrifft eine Abweichung zwischen Requirement 3.2.4 und
  dem Design von `allocate_car`, die LLM-Meldung ein fehlendes Signal
  zur Bestätigung der Fahrzeugzuweisung.
- **ID 6 (`rejected`, t = 0,60)**: Gleicher Signalname, aber anderer
  Defekt. Der Goldstandard betrifft die fehlende Information *Estimated
  time* im Signal `confirm`, die LLM-Meldung dagegen ein nicht
  definiertes Confirm-Signal für die Auftragsübermittlung.
- **ID 32 (`rejected`)**: Gleicher Signalname und gleiche Location, aber
  anderer Defekt. Der Goldstandard verlangt die Änderung von
  `Start_voice` zu `send_voice`, die LLM-Meldung beschreibt dagegen eine
  unnötige Wiederholung des Signals.
- **ID 38 (`rejected`)**: Gleicher allgemeiner Signalbegriff und gleiche
  Location, aber anderer Defekt. Der Goldstandard verlangt die Änderung
  von `Order` zu `OrderOper` samt fehlendem Parameter, die LLM-Meldung
  beschreibt dagegen ein fehlendes Rejection-Signal.

## Bedeutung für die Ergebnis- und Kostenanalyse

Die final festgelegten manuellen Bewertungsentscheidungen bilden die
maßgebliche fachliche Bewertungsgrundlage. Automatische
Zuordnungskandidaten sind keine bestätigten Treffer. Kostenkennzahlen
pro bestätigtem Goldstandard-Treffer beruhen auf der Zahl
unterschiedlicher `confirmed`-IDs (`human_confirmed_union_tp` in der
Human-Summary). Listenpreisbasierte USD-Kosten und reale Tokenusage
liegen unter `results/costed_split_soft_n10/costs/` vor.
