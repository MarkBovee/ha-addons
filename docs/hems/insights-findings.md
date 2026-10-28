# Bevindingen: verkooppauzes, vergelijking met de oude manager, scope van Insights (28 okt 2026)

Alleen onderzoek; er is niets aan de planner veranderd.

## 1. Verkopen met pauzes (open punt 3)

Plan van 28 okt: verkoop 16:30–19:30 (12 kwartieren), 9 actief, 3 rustkwartieren. Laden 12:00–15:15 in 4 stukken.

- **Wat de pauzes opleveren.** De rustkwartieren zijn de goedkoopste in het blok (17:30 € 0,5439, 17:45 € 0,5408). De beste 9 kwartieren
  tegenover het beste aaneengesloten blok van 9 scheelt € 0,0031/kWh. Bij 15,85 kWh is dat **ongeveer € 0,05 per dag**.
- **Wat ze kosten.** Elke pauze is een extra SAJ-ontlaadslot. Vandaag: 3 ontlaadsloten in plaats van 1, en 4 laadsloten. De SAJ heeft er
  7 van elk, en het plan beslaat 48 uur. De pauzes nemen dus sloten die een tweede venster (morgenochtend) nodig heeft.
- **Voorstel:** een regel in `windows.py`/`slots.py`: een gat korter dan N kwartieren wordt gevuld als het verschil kleiner is dan een
  drempel per extra slot (startwaarde € 0,10). Hetzelfde geldt voor laden. Dit is pas meetbaar met de replay over de dagen sinds 17 okt;
  die meting is de volgende stap, vóór fase 3.

## 2. HEMS en de oude manager: 4 van 50 kwartieren eens, −€ 1,93 (open punt 4)

Twee oorzaken, allebei in de **meting**, niet in de planner.

### 2.1 De vergelijking telt verschillende woorden als verschillende acties

`otherAction()` in `hems-panel.js` zet de status van `sensor.battery_manager_current_action` om. Historie van 28 okt laat zien wat dat
oplevert:

| Status van BM | Wat de batterij doet | `otherAction` | HEMS zou zeggen |
| --- | --- | --- | --- |
| `Adaptive (discharge to 0W export)`, `Adaptive (grid-follow starting)` | huis dekken, niets naar het net | discharge (haakjes weg, geen W) | idle |
| `Adaptive 600W` | huis dekken | discharge | idle |
| `Adaptive 8000W` | verkopen | discharge | discharge |
| `Opportunistic Solar (2386W excess)` | PV-overschot laden | charge | idle (self-consumption laadt ook PV) |
| `Passive Solar (0W charge gap)`, `Adaptive 0W` | niets | idle | idle |

`idle` in HEMS betekent self-consumption: het huis dekken en PV-overschot laden. BM noemt dat "Adaptive" en "Opportunistic Solar". Het
grootste deel van de dag is BM dus "discharge" of "charge" waar HEMS "idle" zegt. Daarbij komt dat er één monster per kwartier is, genomen
aan het begin; BM wisselt per minuut (`grid-follow starting` → `0W` → …).

**Voorstel:** naar netintentie indelen: `Charging …` = charge, `Discharging …` of `Adaptive ≥ 2000 W` = discharge, de rest idle. Daarna
meet de vergelijking echte verschillen, zoals vandaag: BM laadt 11:30–15:30 op 2 kW en verkoopt 17:30–19:30 op 8 kW; HEMS laadt 12:00–15:15
in stukken en verkoopt 16:30–19:30.

### 2.2 "Saved" is het resultaat van BM, niet van HEMS

`realised.py` meet wat er echt gebeurde aan de meter. In dry-run stuurt BM de batterij, dus −€ 1,93 (vandaag −€ 2,55 tot 11:46) is
**wat BM's aansturing kost tegenover self-consumption**. Twee dingen maken het getal binnen een dag bovendien schever:

- Laden telt meteen als kosten; de verkoop volgt 's avonds. Halverwege de dag staat een laaddag altijd in de min.
- Aan het eind van de dag telt energie die nog in de batterij zit niet mee (de baseline heeft andere opslag). De terminale waarde die
  de planner al gebruikt (`terminal.py`) zou dat rechttrekken.

**Voorstel:** in dry-run het label "Saved" vervangen door "Battery manager vs self-consumption" en per dag het verschil in opgeslagen
energie waarderen met de terminale waarde. Het getal van HEMS zelf is pas te meten na fase 4 (advisory/auto); tot dan alleen het
geplande `expected_saving` tonen.

## 3. Insights per dag, week, maand en jaar (open punt 5)

Huidige beperking: `realised.py` bewaart kwartieren 8 dagen (`KEEP_DAYS`); de dagtotalen (`daily`) groeien wel door.

- **Dag:** bestaat (kwartieren).
- **Week / maand:** optellen van `daily`. Eén keuzeknop in Insights (`Day · Week · Month · Year`), staafjes per dag of per week.
- **Jaar:** dagtotalen worden klein (€, kWh in/uit, PV, huis) — 365 regels in de Store is geen probleem. Geen kwartieren bewaren.
- **Nodig per dagtotaal:** kosten, baseline-kosten, import/export kWh, PV, huis, laadverlies en de terminale correctie (2.2), zodat
  week, maand en jaar uit dezelfde regels komen.
- **Fasering:** eerst 2.1 en 2.2 (anders telt de week de verkeerde getallen op), dan de dagtotalen uitbreiden, dan de keuzeknop.
- **Alternatief:** HA long-term statistics (`recorder`) voor import/export. Die heeft geen baseline en geen prijs per kwartier van HEMS,
  dus de eigen dagtotalen blijven de bron; statistics alleen als controle.
