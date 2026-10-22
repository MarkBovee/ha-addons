# HEMS dry-run, weekoverzicht 13 tot 20 okt 2026 (gemaakt 21 okt 2026)

Gebaseerd op de dagrapporten (13 tot 17 okt, 18+19 okt gecombineerd, 20 okt) en de replays. Cijfers van 13 tot 19 okt komen uit die rapporten, niet opnieuw berekend; alleen 20 okt is nu vers uitgerekend. Het margeexperiment (beide kanten 0,08) heeft alleen 20 okt deels (vanaf 09:05) en 21 okt nog niet volledig gedekt, dus de vergelijking planner-tegen-planner is nog dun.

**Samenvatting**
1. HEMS-gezondheid is de hele week goed: elk kwartier een besluit, prijsafwijking 0,0001, nul planner- of executorfouten na de fixes van 15 en 16 okt. Open punt dat niet bij HEMS ligt: veel Home Assistant-herstarts (13 op 18+19 okt, 5 op 20 okt, 4 op 21 okt).
2. De uitkomst hangt aan de marge en aan de BM-fixes, niet aan een planfout: HEMS bij 0,12 doet op dunne dagen vrijwel niets, bij 0,08 is de replay beter dan BM (20 okt +2,32 tegen +1,49; 14 tot 19 okt +11,06 tegen +7,28 volgens de eerdere studie). BM gedraagt zich sinds 0.9.7 tot 0.9.9 steeds meer als de HEMS-planner.
3. Aanbeveling: **nog niet** laten schrijven. Eerst één of twee volle dagen met werkelijk gelijke instellingen (BM staat op rendement 1,0 en sell-wait uit), zie onder.

## Dagoordelen

| Dag | Oordeel | Opmerking |
|---|---|---|
| 13 okt (deels) | gezond | 87 kwartieren; HEMS hield de energie vast voor de ochtendpiek, BM verkocht de avond |
| 14 okt | gezond, BM miste beide pieken | BM 0.8.87/0.9.0/0.9.1; geschat gemist 1,4 + 2,5 EUR; HEMS-bug in 5 redentexten (later gefixt) |
| 15 okt | gezond | beide pieken verkocht (BM 0.9.3 tot 0.9.6); nachtlading BM 0,334 voor dunne ochtendpiek; venstergegevens tot 0797222 fout |
| 16 okt | gezond | 8 herstarts door eigen deploys; marge 0,12 vanaf 09:47 |
| 17 okt | gezond | beide kanten verkopen de avond; HEMS ochtend niet (marge/houden) |
| 18 okt | gezond (HA-herstarts) | beide kanten verkopen de avondpiek |
| 19 okt | gezond (HA-herstarts) | beide pieken door beide verkocht; BM begint steeds vroeg |
| 20 okt | gezond | zie `2026-10-20.md`: avond door beide, ochtend alleen BM |

## Wie had gelijk (HEMS en echte batterij)

Replay (orakel, per dag), cash vs. geen batterij:

| Dag | HEMS m0,12 | m0,10 | m0,08 | m0,05 | echt (BM) |
|---|---|---|---|---|---|
| 17 okt | +0,05 | +0,43 | +1,01 | +1,52 | +0,42 |
| 18 okt | +0,00 | +0,00 | +1,70 | +2,02 | +0,79 |
| 19 okt | +0,00 | +0,00 | +0,00 | +0,00 | +1,04 |
| 20 okt | +0,00 | +1,88 | +2,32 | +2,32 | +1,49 |
| totaal 17 tot 20 | +0,05 | +2,31 | +5,03 | +5,86 | +3,74 |

- Bij 0,08 haalt de planner in vier dagen meer dan BM; de uitzondering is 19 okt (dunne spread 0,116, de planner doet dan niets, BM verdient +1,04).
- Verschillen in gedrag waren op 14 tot 16 okt vooral BM-bugs (0.9.0 tot 0.9.6), vanaf 17 okt de marge. Waar HEMS en BM uiteenliepen bij een nachtlading, kreeg HEMS achteraf gelijk: 19 okt (0,34 voor 0,443) en 20 okt (0,337 voor 0,419) leverden BM minder dan de marge op; 0.9.7 tot 0.9.9 sluiten dat. De 18 okt-lading (0,286 tot 0,296 voor 0,50) was wel winstgevend en HEMS laadde niet (marge 0,12), dus daar had BM gelijk.
- De ochtendpieken zijn het structurele verschil: BM verkoopt ze vroeg (19 okt 07:00 op 0,448 voor top 0,511; 20 okt 07:00 op 0,39 voor 0,456), HEMS wacht en mist hem als BM de voorraad al heeft gebruikt of op nabije missen (17 okt, 20 okt).

## Piekdekking per dag

| Dag | BM | HEMS |
|---|---|---|
| 14 okt | geen van beide (0.8.87 tot 09:40; avond verdween door 0.9.1-bug) | beide gepland |
| 15 okt | beide verkocht | beide gepland; ochtend 0,489 net onder drempel |
| 17 okt | avond ja, ochtend ja (4,4 kWh) | avond ja, ochtend nee |
| 18 okt | avond ja | avond ja |
| 19 okt | beide ja | beide ja (ochtend 0,91 kWh, avond 9 kWh) |
| 20 okt | beide ja (8,9 + 16,9 kWh) | avond ja (11,6 kWh), ochtend gepland 6,3 kWh maar niet uitgevoerd |

Op geen dag liet HEMS-plan een winstgevende piek liggen zonder dat de marge, het rendement of de voorraad het verklaarde. BM liet op 14 okt twee pieken liggen (versies, inmiddels opgelost).

## Plannen en wachtkosten

- Geen planfladder: 4 `action_changed` en 2 tot 5 `plan_shift` per dag, geen executor-flapperen na de fix van 15 okt.
- Laad-en-verkoop-planning over meer dan 8 uur komt nauwelijks voor (HEMS laadt in de middag voor de avond); het plan van een nacht ervoor wordt niet gevolgd omdat de dry-run de batterij niet beweegt.
- Wachtkosten (`hold_cost_kwh_h` 0,002): de replay is gevoelig. 17+18 okt: uit +0,76, 0,002 +0,43 (tegen echt +0,42), 0,005 +0,03; 20 okt: uit +1,75, 0,001 en 0,002 +1,88, 0,005 +0,00. Er zit een cliff tussen 0,002 en 0,005. Aanbeveling: 0,002 houden, 0,001 is een veilige verlaging (net zo goed of beter op 20 okt), 0,005 niet gebruiken. Geen verandering van de default nodig.

## Voorspelling

| Dag | Belasting MAE | bias | PV MAE | PV bias |
|---|---|---|---|---|
| 17 okt | 0,391 | -0,244 | 0,208 | +0,165 |
| 18 okt | 0,440 | -0,207 | 0,078 | 0,000 |
| 19 okt | 0,359 | +0,084 | 0,191 | +0,113 |
| 20 okt | 0,195 | +0,004 | 0,103 | -0,080 |

- Belasting wordt beter na boiler-fix 1.2.13 en de modulevoorspelling; PV-bias wisselt van teken (nog geen kalibratie nodig). De regel "bias > 0,2 kWh/u gedurende 3 dagen" is niet gehaald.

## Aanbeveling: HEMS laten schrijven?

**Nog niet, om drie redenen.**
1. Het margeexperiment is niet zuiver: BM draait op `round_trip_efficiency` 1,0 (default 0,9) en `sell_wait_for_better_morning_enabled` false, HEMS op rendement 0,82. Een vergelijking op "gelijke marge" laat dus vooral het rendement zien. Eerst gelijkzetten (of bewust het verschil benoemen) en één volledige dag meten (21 okt is begonnen).
2. Het bewijs van de planner is replay (orakel) plus plan-vergelijkingen op de echte SoC. De dry-run volgt zijn eigen plan nooit, dus een gesloten lus (HEMS laadt, verkoopt, SoC volgt) is nog niet getest, ook niet voor de executor bij een lege batterij.
3. De HEMS-gezondheid is goed, maar de omgeving niet: Home Assistant herstart veel, en bij een schrijfmodus hoort een duidelijk antwoord wat er gebeurt met een half verstuurde opdracht bij een herstart (HEMS zelf herstelt na 60 s).

Als Mark toch wil: eerst een korte, begeleide proef (één dag, `idle` terugvallen bij `no_soc`, BM uit) met HEMS-marge 0,08 en de executor op de vloer 30 %.

## Taak

De bewakingsweek is afgerond: deze geplande taak (`hems-dry-run-monitoring`) kan uitgezet worden; ik heb hem zelf niet aangepast.
