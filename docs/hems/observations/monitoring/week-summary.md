# HEMS dry-run, weekoverzicht 13 tot 25 okt 2026 (gemaakt 26 okt 2026)

Gebaseerd op de dagrapporten (13 tot 25 okt) en de margestudie van 15 tot 25 okt (`scripts/hems_margin_study.py`). De margestudie gebruikt de gemeten load en PV (orakel): het is het plafond van de planner, geen voorspelling. Cijfers van 13 tot 19 okt komen uit eerdere rapporten; 20 tot 25 okt zijn vers uitgerekend.

**Samenvatting**
1. HEMS-gezondheid is de hele periode goed: elk kwartier een besluit, `price_check_max_diff` 0,0001, geen planner- of executorfouten na de fixes van 15 en 16 okt. Veel herstarts van Home Assistant in de eerste week (13 op 18+19 okt, 5 op 20 okt, 11 op 21 okt), niet door HEMS veroorzaakt.
2. Over 15 tot 25 okt haalde de echte batterij (BM) +16,01 EUR, HEMS bij marge 0,08 (orakel) +13,69, bij 0,10 +10,16, bij 0,12 +4,52, bij 0,00 +21,16. Per dag wisselt de winnaar: HEMS op 17, 18, 20 en 23 okt; BM op 16, 19, 21, 22 en 24 okt; 15 en 25 okt gelijk. De uitkomst hangt vooral aan de marge en het rendement (BM rekent met 1,0, HEMS met 0,82), niet aan een planfout.
3. Advies: **nog niet** laten schrijven. Eerst een periode met gelijke instellingen (marge en rendement) en de BM-marge vastleggen per dag.

## Dagoordelen

| Datum | Oordeel | Opmerking |
|---|---|---|
| 13 okt | gezond | eerste dag, beide zijden bepaald door de oude instellingen |
| 14 okt | aandacht | BM 0.9.0 tot 0.9.3: avondpiek gemist door `full`-pauze; zie dagrapport |
| 15 okt | gezond | BM 0.9.4 tot 0.9.5; HEMS en BM bij 0,10 vrijwel gelijk (3,48 tegen 3,56) |
| 16 okt | gezond | marge BM 0,12 vanaf 11:00; HEMS verkoopt dunne dag niet (0,00) |
| 17 okt | gezond | waterverwarming 1.2.13 (UTC-fout gefixt); HEMS-boiler-module van kracht |
| 18 okt | gezond (HA-herstarts) | beide kanten verkopen de avondpiek |
| 19 okt | gezond | BM 0.9.6 tot 0.9.8; BM laadt voor een te dunne verkoop (zie 0.9.7) |
| 20 okt | gezond | marge-experiment start (beide 0,08); avond door beide, ochtend alleen BM |
| 21 okt | gezond (11 herstarts) | eerste volle dag met gelijke marge; HEMS doet bij 0,08 niets in de studie |
| 22 okt | gezond | BM won (+4,31 tegen +3,04); rendement 0,82 tegen 1,0 maakt de ochtendverkoop het verschil |
| 23 okt | gezond | BM verloor (−0,93, verkocht bij lage prijzen); HEMS 0,00 bij 0,08 |
| 24 okt | gezond | BM +1,49 tegen HEMS 0,00 bij 0,08 (HEMS bij 0,00: +1,57) |
| 25 okt | gezond | beide verkochten de hele avondpiek; BM +2,12 tegen HEMS +2,05 bij 0,08; zie `2026-10-25.md` |

## Hoe vaak waren HEMS en de echte batterij het oneens?

Methode: per uur de richting van het HEMS-besluit (gewogen over de kwartieren) tegen de richting van het uurgemiddelde van `sensor.battery_api_battery_power` (drempel 1 kW). Een grove maat: laden door PV telt als laden.

| Datum | Uren oneens (van ±24) | HEMS ontladen kWh | Echte batterij ontladen kWh (>1 kW uren) | HEMS geladen kWh | Echte batterij geladen kWh | Verkochte topkwartieren HEMS (van 8) |
|---|---|---|---|---|---|---|
| 14 okt | 11 | 37,8 | 6,5 | 38,9 | 23,7 | 7 |
| 15 okt | 3 | 24,0 | 32,9 | 17,4 | 27,7 | 8 |
| 16 okt | 16 | 16,3 | 25,2 | 0,0 | 31,0 | 3 |
| 17 okt | 13 | 7,9 | 24,3 | 0,0 | 31,3 | 5 |
| 18 okt | 7 | 2,9 | 11,4 | 0,0 | 20,5 | 3 |
| 19 okt | 9 | 10,0 | 18,9 | 0,0 | 27,4 | 4 |
| 20 okt | 7 | 11,6 | 24,9 | 24,9 | 37,1 | 6 |
| 21 okt | 13 | 39,2 | 19,9 | 1,9 | 31,2 | 3 |
| 22 okt | 9 | 18,6 | 33,0 | 22,6 | 34,8 | 8 |
| 23 okt | 11 | 19,7 | 9,3 | 0,0 | 21,6 | 2 |
| 24 okt | 8 | 15,6 | 19,6 | 0,0 | 30,9 | 8 |
| 25 okt | 7 | 14,5 | 14,7 | 6,4 | 10,5 | 8 |

Lezing van de tabel:
- Het aantal verschillende uren is groot op dagen zonder HEMS-lading: HEMS laadde van de net niet in 16 tot 19 en 23 tot 24 okt, terwijl BM dan wel van het net of uit de PV laadde. Dat is de marge: HEMS vond de inkoop niet waard en de PV vulde de batterij vanzelf.
- Een echte verkoop waar HEMS niets deed: geen dag met een groot gemist blok (zie peakdekking hieronder).
- HEMS ontlaadde 39 kWh op 21 okt. Dat is meer dan de helft van de batterij twee keer; de oorzaak is niet nagekeken (mogelijk meerdere cycli op één dag). Open controle.

## Piekdekking per dag (HEMS)

HEMS verkocht in de topkwartieren (de 8 hoogste exportprijzen van de dag):
- 8 van 8: 15, 22, 24, 25 okt.
- 6 tot 7 van 8: 14, 20 okt.
- 2 tot 5 van 8: 16, 17, 18, 19, 21, 23 okt.

Van de echte batterij is de piekdekking per kwartier niet uitgerekend; de ontlading van de echte batterij staat in de tabel hierboven. Op 25 okt verkocht BM in de drie piekuren 14,7 kWh (zie `2026-10-25.md`). Een gemist profijtelijk piek is dit week niet vastgesteld; de dunne dagen zijn een margevraag.

## Plannen houden stand

- Op 25 okt geen lading gevolgd door verkoop na meer dan 8 uur. Over de week niet systematisch nagekeken (de diff van cycli is per dag handwerk). Open.
- Actie-wisselingen en plan-verschuivingen: 25 okt 11 en 4 op 100 cycli. Geen constant flippen gezien in de dagrapporten.
- Wachtkosten (`hold_cost_kwh_h` 0,002): op 25 okt laadde HEMS pas in de middag, vlak voor de piek (13:45 tot 16:15), en verkocht de avondpiek volledig. Geen verlies door te laat laden gevonden. Advies: de standaard 0,002 blijft voorlopig; geen reden om hem te veranderen.

## Voorspellingskwaliteit

- Basisbelasting 25 okt: MAE 1,89 kWh/u, bias −1,62 (te laag). De nachtelijke verwarmingsbelasting (≈4 kW tegen ≈0,5 kW voorspeld) is de grootste fout en is bekend.
- PV 25 okt: MAE 0,09 kWh/u, bias +0,03. De PV-voorspelling was de week door goed (24 okt MAE 0,23, bias −0,16 op 24 okt zelf).
- De formule uit de taak voor de huisbelasting (`power_usage` plus `saj_total_grid_power`) levert onmogelijke waarden; de meter `sensor.power_usage` moet nog worden gecontroleerd. Tot dan is de omvormer-belasting de maat.

## Geld

| Datum | HEMS-orakel 0,08 | HEMS 0,10 | HEMS 0,12 | Echte batterij |
|---|---|---|---|---|
| 15 okt | +3,58 | +3,48 | +2,40 | +3,56 |
| 16 okt | 0,00 | 0,00 | 0,00 | +1,01 |
| 17 okt | +1,01 | +0,43 | +0,05 | +0,42 |
| 18 okt | +1,70 | 0,00 | 0,00 | +0,79 |
| 19 okt | 0,00 | 0,00 | 0,00 | +1,04 |
| 20 okt | +2,32 | +1,88 | 0,00 | +1,49 |
| 21 okt | 0,00 | 0,00 | 0,00 | +0,70 |
| 22 okt | +3,04 | +2,65 | +1,28 | +4,31 |
| 23 okt | 0,00 | 0,00 | 0,00 | −0,93 |
| 24 okt | 0,00 | 0,00 | 0,00 | +1,49 |
| 25 okt | +2,05 | +1,72 | +0,78 | +2,12 |
| **totaal** | **+13,69** | **+10,16** | **+4,52** | **+16,01** |

Opmerkingen:
- De echte batterij draaide op marge 0,12 tot 20 okt en daarna op 0,08 (sinds 20 okt). Het margeverschil van 0,12 tegen 0,08 is daarom in de studie niet zuiver te vergelijken met de BM-kolom voor 15 tot 19 okt.
- BM rekent met een rendement van 1,0; HEMS met 0,82. Dat verschil geeft BM op verkoopdagen een hogere waarde per kWh en verklaart een deel van de verschillen (22 okt).
- De orakel-replay ligt bij HEMS' gemeten load en PV. Met voorspellingen is HEMS' waarde lager (14 tot 19 okt met logged forecasts: +11,06 tegen +7,28 EUR bij 0,08 eerder gerapporteerd).

## Bevindingen

**Echte bugs**
- Geen nieuwe bug gevonden in de week. De eerder gevonden fouten (14 okt pauze, 15 okt margepoort, 19 okt laadbeslissing, `windows`-fouten) zijn gefixt in de builds na 15 tot 19 okt en tellen niet meer mee.
- Open controle: 21 okt 39 kWh ontladen door HEMS. Nagaan of het meerdere cycli zijn of een meetfout in `power_w` per kwartier.

**Afstellingen en vragen**
1. Marge en rendement: BM op 1,0 en HEMS op 0,82 maken de dagen niet vergelijkbaar. Voorstel: één week met beide op 0,82, of HEMS' rendement op 1,0 zetten in de vergelijking.
2. Marge 0,08 is de planner-keuze op dunne dagen: HEMS verkoopt dan op 16, 19, 21, 23, 24 okt niets, terwijl de echte batterij op 16, 19, 21, 24 okt wel winst maakte. Vraag: moet de marge lager (0,05), of is het juist dat BM op die dagen verlies maakte (23 okt −0,93)?
3. Basisbelasting: de nachtelijke verwarming ontbreekt in de voorspelling. Voorstel: verwarmingsverbruik als aparte verwachting.
4. Meter `sensor.power_usage` moet worden gecontroleerd (eenheid of teken).
5. Herstarts van Home Assistant (in totaal ruim 30 in de periode) maken de logs lastig te lezen en breken de dagreeks; niet door HEMS veroorzaakt.

## Vervolg

De monitoringweek is compleet. Het scheduled task `hems-dry-run-monitoring` kan worden uitgeschakeld; dat laat ik aan Mark. Het HEMS-schrijven naar de batterij is nog niet verantwoord: de uitkomst wisselt per dag, de marge en het rendement van de twee kanten zijn nog niet gelijk gezet, en de planner heeft op het orakel 2,3 EUR minder dan de echte batterij over de periode. Dat is een verschil in instellingen en voorspelling, geen bewijs van een zwakke planner, maar het is ook geen reden om te schrijven.
