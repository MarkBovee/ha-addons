# Marge en reserve: waar HEMS winst laat liggen (17 okt 2026)

Doel (Mark, 17 okt): HEMS moet beter worden dan de huidige battery-manager (BM). Dit is de meting waar dat nu aan hangt. Reproduceren: `python3 scripts/hems_margin_study.py` (alleen lezen, gebruikt de verzamelde uurdata en de prijzen uit de opgehaalde logs).

## Meting

Cash-besparing per dag in EUR ten opzichte van geen batterij, planner per lokale dag vanaf de opgenomen SoC van die dag, echte belasting en PV (een orakel: dit is het plafond van de planner, geen uitkomst met eigen voorspellingen). 13 okt ontbreekt: de prijzen van die dag zijn er maar voor een deel (recorder-export tot 12 okt, geplande logs vanaf 13 okt ~12:30).

| dag | marge 0,00 | 0,03 | 0,05 | 0,08 | 0,10 | 0,12 | 0,05 zonder wachtkosten | 0,05 reserve 5 % | echt (BM) |
|---|---|---|---|---|---|---|---|---|---|
| 7 okt | +1,32 | +0,73 | +0,63 | +0,00 | +0,00 | +0,00 | +0,74 | +1,91 | -1,68 |
| 8 okt | +2,81 | +2,65 | +2,56 | +1,95 | +0,00 | +0,00 | +2,58 | +3,08 | +2,68 |
| 9 okt | +1,37 | +0,88 | +0,51 | +0,00 | +0,00 | +0,00 | +0,71 | +0,51 | +0,76 |
| 10 okt | +3,01 | +2,73 | +2,73 | +2,73 | +2,90 | +2,90 | +2,33 | +3,51 | +1,89 |
| 11 okt | +3,87 | +3,81 | +2,20 | +2,20 | +2,02 | +1,75 | +1,57 | +3,05 | +3,07 |
| 12 okt | +2,53 | +2,36 | +3,69 | +3,18 | +2,81 | +2,84 | +4,84 | +4,40 | +1,71 |
| 14 okt | +5,69 | +5,69 | +5,69 | +5,41 | +5,21 | +5,06 | +5,69 | +6,90 | +0,23 |
| 15 okt | +3,71 | +3,58 | +3,58 | +3,58 | +3,48 | +2,40 | +3,58 | +4,45 | +3,56 |
| 16 okt | +1,24 | +0,84 | +0,37 | +0,00 | +0,00 | +0,00 | +0,72 | +0,77 | +1,01 |
| **totaal (9 dagen)** | **+25,54** | **+23,27** | **+21,97** | **+19,05** | **+16,43** | **+14,95** | **+22,75** | **+28,59** | **+13,22** |

## Wat dit zegt

1. **Bij marge 0,12 is HEMS niet beter dan BM, zelfs met perfecte voorkennis**: +14,95 tegen +13,22 EUR in negen dagen. Met echte voorspellingen wordt dat alleen slechter. De marge is de grootste hendel.
2. **Elke 0,01 marge kost ruwweg 0,7 tot 1,0 EUR per negen dagen.** 0,12 naar 0,05: +7,0 EUR (+47 %). 0,12 naar 0,00: +10,6 EUR. De dagen met een dunne spread (7, 9 en 16 okt) doet de planner bij marge 0,08 of hoger niets, terwijl BM daar +0,76 en +1,01 haalt (7 okt: -1,68).
3. **Reserve 30 % naar 5 % (bij marge 0,05)** voegt nog +6,6 EUR toe (+28,59). Dat is een veiligheidskeuze van Mark (huis niet leegtrekken); het getal is wat die keuze kost.
4. **Wachtkosten 0,002** (bij marge 0,05): -0,7 EUR over negen dagen tegenover geen wachtkosten (+22,75 tegen +21,97); in de eerdere replay won de waarde op het totaal van acht dagen. Niet de eerste hendel.
5. **14 okt** (+5,69 tegen +0,23) is de dag waarop BM de avondpiek miste (bekende bug, hersteld in 0.9.1); die dag is geen eerlijke vergelijking.

## Beperkingen

- Orakel: echte belasting en PV. Het verschil met de live dry-run (eigen voorspellingen, PV 16 okt 65 % te laag) is niet gemeten; de live SoC volgt BM, dus de dry-run kan dit niet laten zien. Een replay met de gelogde voorspellingen per cyclus (`plans.jsonl` heeft `load` en `pv` per cyclus) is de volgende stap.
- Per dag vanaf de opgenomen SoC, geen doorlopende keten; de waarde van de SoC aan het eind is de 20e percentiel van de inkoopprijs.
- De marge is geen kostenpost: de besparing is cash. Wat marge beschermt (voorspelfout, slijtage van de batterij) staat nergens als getal; zolang dat zo is, is de keuze tussen 0,12 en 0,05 een inschatting, geen berekening.

## Voorstel

Eén beslissing van Mark per hendel, in deze volgorde van opbrengst:
1. **Marge naar 0,05** voor de rest van de proefweek (HEMS blijft dry-run, BM blijft 0,12): het verschil wordt dan echt zichtbaar in de dagrapporten, zonder dat het geld kost.
2. **Slijtage als getal**: de prijs van de batterij gedeeld door cycli en bruikbare kWh geeft een slijtagekost per kWh. Is dat 0,03, dan hoort de marge ongeveer daar en niet op 0,12; is het 0,08, dan klopt 0,12 bijna.
3. **Reserve** pas aanpassen als 1 en 2 bevestigd zijn.

## Aanvulling 20 okt: doorlopende keten en de schaarste van de capaciteit

Opmerking van Mark: je kunt niet meer verkopen dan er in zit (100 % naar de ondergrens van 30 % is ongeveer 15 tot 17,5 kWh, één cyclus), dus een lage marge verkoopt alles al vóór de grote pieken. De marge is daarmee vooral de prijs van die schaarse dagcapaciteit, niet van slijtage (slijtage uit €7000 en 90 % na 10 jaar: ongeveer €0,01 per kWh).

De eerste studie speelde elke dag los af. Hieronder dezelfde planner als doorlopende keten (eigen SoC meegenomen, prijzen zoals gepubliceerd, rolling horizon), cash in EUR en kWh per dag aan de batterij:

| Marge | 7 tot 12 okt cash | kWh/dag | 14 tot 19 okt cash | kWh/dag |
|---|---|---|---|---|
| 0,00 | +14,90 | 29,7 | +15,46 | 27,4 |
| 0,03 | +13,16 | 18,6 | +14,72 | 21,2 |
| 0,05 | +12,33 | 14,8 | +13,80 | 17,9 |
| 0,08 | +10,06 | 9,5 | +10,87 | 11,3 |
| 0,10 | +7,74 | 5,8 | +8,93 | 8,6 |
| 0,12 | +7,49 | 5,3 | +7,83 | 7,2 |
| echt (BM) | +8,42 | | +7,28 | |

Lezing: bij marge 0,05 verkoopt de planner ongeveer een volle bruikbare cyclus per dag (15 tot 18 kWh); onder 0,05 komen er tweede cycli bij op kleine spreads (0,00: ruim 1,5 cyclus per dag) en de winst per extra kWh daalt snel (0,05 naar 0,00: +2,6 en +1,7 EUR in zes dagen). Boven 0,05 blijft capaciteit onbenut (0,10: ongeveer een halve cyclus). Een grotere piek na de horizon (de dag na morgen) kent de planner niet; zijn restwaarde voor energie aan het eind van de horizon is de goedkoopste inkoopprijs binnen de horizon (`terminal_value` in `battery.py`). Dat is de plek waar Marks punt in te bouwen is: een restwaarde uit de pieken van de laatste dagen in plaats van uit de goedkoopste inkoop, zodat een lagere marge niet alles voor de volgende piek leegverkoopt.
