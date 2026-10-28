# HEMS dry-run, weekoverzicht 13 tot 26 okt 2026 (bijgewerkt 27 okt 2026)

Gebaseerd op de dagrapporten (13 tot 26 okt) en de margestudie van 14 tot 26 okt (`scripts/hems_margin_study.py`). De margestudie gebruikt de gemeten load en PV (orakel): het is het plafond van de planner, geen voorspelling. Cijfers van 13 tot 19 okt komen uit eerdere rapporten; 20 tot 26 okt zijn opnieuw uitgerekend.

**Samenvatting**
1. HEMS-gezondheid is goed: elk kwartier een besluit, `price_check_max_diff` 0,0001, geen planner- of executorfouten na de fixes van 15 en 16 okt. Wel kwam de koppeling in de hele periode vaak opnieuw op (13 op 18 en 19 okt, 5 op 20 okt, 11 op 21 okt, 14 op 26 okt). Die herinitialisaties vallen op de minuut samen met een korte `unknown` op de BM-sensor, dus een uitval van de batterijdata. Eerder schreef ik dat aan herstarts van Home Assistant toe; voor 26 okt klopt dat niet, en voor de andere dagen is het niet nagekeken.
2. Over 15 tot 26 okt haalde de echte batterij (BM) +19,90 EUR, HEMS bij marge 0,08 (orakel) +20,14, bij 0,10 +15,98, bij 0,12 +9,81, bij 0,00 +27,61. Per dag wisselt de winnaar: HEMS op 17, 18, 20, 23 en 26 okt; BM op 16, 19, 21, 22 en 24 okt; 15 en 25 okt gelijk. De uitkomst hangt vooral aan de marge en het middagladen, niet aan een planfout (26 okt: 2,56 EUR verschil bij gelijke marge, grotendeels laden om 12:00).
3. Advies: **nog niet** laten schrijven. Eerst een periode met gelijke instellingen (marge en rendement) en de BM-marge en -redenen per dag vastleggen. Ook de boiler-voorspelling (26 okt) en de PV-bias (26 okt +57 %) moeten eerst kloppen.

## Versies en instellingen per deel van de periode

- BM 0,9,0 tot 0,9,3: 14 okt (zie dagrapport 14 okt). 0,9,4 en 0,9,5 op 15 okt, 0,9,6 op 15 okt (changelog).
- BM 0,9,6 tot 19 okt 20:11; 0,9,7 tot 20:22; 0,9,8 tot 20 okt 08:01; **0,9,9 sinds 20 okt 08:01** (`update.battery_manager_update`, installed_version). Alle dagen vanaf 20 okt draaien op 0,9,9.
- Marge BM: 0,12 vanaf 16 okt 11:00, 0,08 vanaf 20 okt (Marks instructie; de add-on-opties zijn in deze run niet gelezen).
- Marge HEMS: 0,10 tot 16 okt 09:47; 0,12 tot 20 okt 08:09; 0,10 tot 20 okt 09:05; **0,08 sinds 20 okt 09:05** (CEST, instellingen-events).
- HEMS-build: `f7fe42b` tot 22 okt 08:16, `cb3d4ce` daarna (voegt `future_peak_haircut` = 0,0 toe aan de snapshot; geen waardewijziging).

## Dagoordelen

| Datum | Oordeel | Opmerking |
|---|---|---|
| 13 okt | gezond | eerste dag, beide zijden bepaald door de oude instellingen |
| 14 okt | aandacht | BM 0.9.0 tot 0.9.3: avondpiek gemist door `full`-pauze; zie dagrapport |
| 15 okt | gezond | BM 0.9.4 tot 0.9.5; HEMS en BM bij 0,10 vrijwel gelijk (3,48 tegen 3,56) |
| 16 okt | gezond | marge BM 0,12 vanaf 11:00; HEMS verkoopt dunne dag niet (0,00) |
| 17 okt | gezond | waterverwarming 1.2.13 (UTC-fout gefixt); HEMS-boiler-module van kracht |
| 18 okt | gezond | beide kanten verkopen de avondpiek; herinitialisaties (HA-herstart niet bevestigd) |
| 19 okt | gezond | BM 0.9.6 tot 0.9.8; BM laadde voor een te dunne verkoop (zie 0.9.7) |
| 20 okt | gezond | marge-experiment start (beide 0,08); avond door beide, ochtend alleen BM |
| 21 okt | gezond (11 herinitialisaties) | eerste volle dag met gelijke marge; HEMS doet bij 0,08 niets in de studie |
| 22 okt | gezond | BM won (+4,31 tegen +3,04); rendement 0,82 tegen 1,0 maakt de ochtendverkoop het verschil |
| 23 okt | gezond | BM verloor (−0,93, verkocht bij lage prijzen); HEMS 0,00 bij 0,08 |
| 24 okt | gezond | BM +1,49 tegen HEMS 0,00 bij 0,08 (HEMS bij 0,00: +1,57) |
| 25 okt | gezond | beide verkochten de hele avondpiek; BM +2,12 tegen HEMS +2,05 bij 0,08; zie `2026-10-25.md` |
| 26 okt | aandacht | 14 herinitialisaties (BM-sensor `unknown`); beide verkochten beide pieken; HEMS +6,45 tegen BM +3,89 bij 0,08, grotendeels middagladen; boiler-run van 1,9 kWh die niet kwam; zie `2026-10-26.md` |

## Hoe vaak waren HEMS en de echte batterij het oneens?

Methode: per uur de richting van het HEMS-besluit (gewogen over de kwartieren) tegen de richting van het uurgemiddelde van `sensor.battery_api_battery_power` (drempel 1 kW). Een grove maat: laden door PV telt als laden. De rijen 14 tot 25 okt zijn met dezelfde aanpak uitgerekend als eerder; bij een herberekening van 26 okt kwam ik op 5 van 24, met een iets andere weging dan de eerdere rijen. Vergelijk daarom binnen een rij, niet tussen rijen.

| Datum | Uren oneens (van ±24) | HEMS ontladen kWh (plan) | Echte batterij ontladen kWh (>1 kW uren) | HEMS geladen kWh (plan) | Echte batterij geladen kWh | Verkochte topkwartieren HEMS (van 8) |
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
| 26 okt | 5 | 21,7 | 15,2 | 49,4 | 19,1 | 8 |

Lezing van de tabel:
- Het aantal verschillende uren is groot op dagen zonder HEMS-lading: HEMS laadde van het net niet op 16 tot 19 en 23 tot 24 okt, terwijl BM dan wel van het net of uit de PV laadde. Dat is de marge: HEMS vond de inkoop niet waard en de PV vulde de batterij vanzelf.
- Op 26 okt was de grootste bron van verschil het middagladen (11:15 tot 14:00, HEMS wel, BM niet). De ochtend en de avond kwamen overeen, behalve dat BM om 08:16 stopte met verkopen bij 57,9 % SoC terwijl HEMS nog een uur doorging.
- HEMS ontlaadde 39 kWh op 21 okt. Dat is meer dan de helft van de batterij twee keer; de oorzaak is niet nagekeken (mogelijk meerdere cycli op één dag). Open controle. De getallen zijn sommen van kwartier-besluiten en geen energiebalans; de planner kan dezelfde energie meerdere keren laten doorlopen.

## Piekdekking per dag (HEMS)

HEMS verkocht in de topkwartieren (de 8 hoogste exportprijzen van de dag):
- 8 van 8: 15, 22, 24, 25, 26 okt.
- 6 tot 7 van 8: 14, 20 okt.
- 2 tot 5 van 8: 16, 17, 18, 19, 21, 23 okt.

Van de echte batterij is de piekdekking op kwartierniveau niet uitgerekend. Op uurniveau (grof: een topkwartier telt als gedekt als het uur over 1 kW ontlaadde) haalde BM op 26 okt 8 van 8, op 25 okt 8 van 8 en op 21 okt 6 van 8. Op 25 okt verkocht BM in de drie piekuren 14,7 kWh (zie `2026-10-25.md`). Een gemist profijtelijk piek is dit week niet vastgesteld; de dunne dagen zijn een margevraag.

## Plannen houden stand

- Op 25 en 26 okt geen lading gevolgd door verkoop na meer dan 8 uur (26 okt: 0 van 96 cycli). Over de hele week niet systematisch nagekeken (de diff van cycli is per dag handwerk). Open.
- Actie-wisselingen en plan-verschuivingen: 25 okt 11 en 4 op 100 cycli; 26 okt 15 en 6 op 110 besluiten. Geen constant flippen gezien in de dagrapporten.
- Wachtkosten (`hold_cost_kwh_h` 0,002): op 25 okt laadde HEMS pas in de middag, vlak voor de piek (13:45 tot 16:15), en verkocht de avondpiek volledig. Op 26 okt laadde HEMS 02:30 tot 05:45 op de goedkoopste kwartieren (0,147 tot 0,171) en verkocht de avondpiek. Geen verlies door te laat laden gevonden. Advies: de standaard 0,002 blijft voorlopig.

## Voorspellingskwaliteit

- Basisbelasting 25 okt: bij herberekening met de cyclus van 00:00 MAE 2,9 kWh/u en bias −2,9 (te laag). Het verschil met het eerdere getal (MAE 1,9, bias −1,6) zit in de keuze van cyclus en in de formule. De formule (`power_usage` plus `saj_total_grid_power` min EV) en `sensor.battery_api_load_power` zijn het oneens; op 26 okt stond de laatste 's nachts op 0 W. De nachtelijke verwarmingsbelasting blijft de grootste fout.
- Basisbelasting 26 okt: MAE 0,26 kWh/u, bias +0,04 (18,0 voorspeld tegen 17,1 gemeten). Zie `2026-10-26.md`.
- PV 25 okt: MAE 0,09 kWh/u, bias 0,00. PV 26 okt: MAE 0,21 kWh/u, bias +0,16; totaal 10,5 voorspeld tegen 6,7 kWh (+57 %). Over de week wisselt de PV-bias van teken; 24 okt MAE 0,25, bias −0,22.
- Boiler: de module plande op 26 okt een run van 1,9 kWh om 12:00. De echte boiler stond tot 18:00 op 0 Wh. Vraag: leest de module de opslagtemperatuur, of plant hij elke dag?

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
| 26 okt | +6,45 | +5,82 | +5,29 | +3,89 |
| **totaal 15 tot 26 okt** | **+20,14** | **+15,98** | **+9,81** | **+19,90** |

Opmerkingen:
- De echte batterij draaide op marge 0,12 tot 20 okt en daarna op 0,08. Het margeverschil van 0,12 tegen 0,08 is daarom in de studie niet zuiver te vergelijken met de BM-kolom voor 15 tot 19 okt. Vanaf 20 okt staan beide kanten op 0,08.
- BM rekent met een rendement van 1,0; HEMS met 0,82. Dat verschil geeft BM op verkoopdagen een hogere waarde per kWh en verklaart een deel van de verschillen (22 okt). Of BM met 1,0 meer had moeten laden op 26 okt, is niet nagegaan.
- De orakel-replay ligt bij HEMS' gemeten load en PV. Met voorspellingen is HEMS' waarde lager. Op 26 okt is het HEMS-plan van 00:00 zelf +6,21 EUR (forecast-gedreven), dus ook dat is het orakel-niveau.
- Dagen waar het orakel 0,00 geeft terwijl BM wel verdiende (21, 24 okt): de oorzaak is niet ontleed. Mogelijk spelen het begin-SoC en de PV-verkoop mee; dat is open.

## Bevindingen

**Echte bugs**
- Geen planner-bug gevonden in de week. De eerder gevonden fouten (14 okt pauze, 15 okt margepoort, 19 okt laadbeslissing, `windows`-fouten) zijn gefixt in de builds na 15 tot 19 okt en tellen niet meer mee.
- Koppeling (26 okt): 14 herinitialisaties op de minuut van een korte `unknown` op de BM-sensor. Geen reload-trigger in de code gevonden. Actie: de HA-logs direct na zo'n dag bewaren en nagaan of de batterij-SoC-sensor wegvalt; overweeg een korte uitval te overbruggen met de laatste waarde.
- Boiler-module (26 okt): een run van 1,9 kWh om 12:00 die niet kwam. Actie: nagaan of de module de echte opslagtemperatuur gebruikt.
- Collector (26 okt): het uurgemiddelde van de import- en exportprijs in `hourly.jsonl` komt niet overeen met de prijscurve (03:00: 0,020 tegen 0,148). Actie: de prijsstatistiek nakijken.
- Replay-tooling: `hems_replay.py` leest prijzen na 12 okt niet uit `plans.jsonl`; de margestudie wel.
- Open controle: 21 okt 39 kWh ontladen door HEMS. Nagaan of het meerdere cycli zijn of een meetfout in `power_w` per kwartier.

**Afstellingen en vragen**
1. Marge en rendement: BM op 1,0 en HEMS op 0,82 maken de dagen niet vergelijkbaar. Voorstel: één week met beide op 0,82, of HEMS' rendement op 1,0 zetten in de vergelijking.
2. Marge 0,08 is de planner-keuze op dunne dagen: HEMS verkoopt dan op 16, 19, 21, 23, 24 okt niets, terwijl de echte batterij op 16, 19, 21, 24 okt wel winst maakte. Vraag: moet de marge lager (0,05), of is het juist dat BM op die dagen verlies maakte (23 okt −0,93)?
3. Middagladen (26 okt): HEMS laadde op 0,26 tot 0,28 voor de avondverkoop van 0,44; BM niet. Dat is het grootste verschil van de dag (±2,5 EUR orakel). De BM-reden is niet terug te vinden; dat vraagt om BM-logs die direct worden opgeslagen.
4. Reserve 30 % (26 okt): ±2 kWh bleef onverkocht bij 0,38 tot 0,43 terwijl BM tot ±22 % ging. Vraag: is 30 % een harde vloer, of hoort de reserve als kostenterm in de planner?
5. Basisbelasting: de nachtelijke verwarming ontbreekt of is onbetrouwbaar in de voorspelling. Voorstel: verwarmingsverbruik als aparte verwachting.
6. Meter `sensor.power_usage` en `sensor.battery_api_load_power` moeten worden gecontroleerd (eenheid, teken en nachtwaarden).
7. Herinitialisaties van de HEMS-koppeling (in totaal ruim 40 in de periode) maken de logs lastig te lezen en breken de dagreeks, zonder dat HEMS een besluit mist. Oorzaak nog open.

## Vervolg

De monitoringweek is compleet. Het scheduled task `hems-dry-run-monitoring` kan worden uitgeschakeld; dat laat ik aan Mark. Het HEMS-schrijven naar de batterij is nog niet verantwoord: de uitkomst wisselt per dag, de marge en het rendement van de twee kanten zijn nog niet gelijk gezet, en de planner heeft op het orakel 2,56 EUR minder dan de echte batterij op 26 okt, waarvan het grootste deel uit het middagladen komt. Dat is een verschil in gedrag en instellingen, geen bewijs van een zwakke planner, maar het is ook geen reden om te schrijven.
