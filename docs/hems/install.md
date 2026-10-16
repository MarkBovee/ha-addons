# HEMS dry-run installeren op Home Assistant

HEMS v0.1 plant elk kwartier wat de batterij zou moeten doen, publiceert dat als sensoren en schrijft per kwartier één regel in een trace. Het **schrijft nooit naar een apparaat**: battery-manager en battery-api blijven de batterij sturen. Doel: een paar dagen naast de bestaande sturing draaien en vergelijken.

Getest tegen Home Assistant 2026.9.4 (de versie op de server) met `pytest-homeassistant-custom-component` 0.13.367.

## Installeren

Snelste route: `python3 hems/deploy.py --dry-run` en daarna `python3 hems/deploy.py` (details en sleutel-instelling in `hems/AGENTS.md`). Het script leest alleen `HA_HOST`, `HA_SSH_USER` en optioneel het pad `HA_SSH_KEY` uit `.env`, nooit een wachtwoord; zonder sleutel vraagt ssh één keer om het wachtwoord. Handmatig kan ook:

1. Kopieer de map `custom_components/hems/` uit deze repo naar `/config/custom_components/hems/` op de HA-server (Samba-share `config`, of via de SSH-add-on). De submap `engine/` hoort erbij: dat is een gegenereerde kopie van `hems/core`.
2. Herstart Home Assistant (een nieuwe integratie wordt pas na een herstart gevonden).
3. Instellingen, Apparaten en diensten, Integratie toevoegen, **HEMS**. Kies de entiteiten:

| Rol | Entiteit in deze installatie | Opmerking |
|---|---|---|
| Batterij laadtoestand | `sensor.battery_api_battery_soc` | |
| Batterijvermogen | `sensor.battery_api_battery_power` | schakelaar "positief bij ontladen" aan laten |
| PV-vermogen | `sensor.battery_api_pv_power` | |
| Netvermogen | `sensor.power_usage` | positief = import |
| AC-uitgang omvormer (optioneel) | `sensor.saj_total_grid_power` | geeft het huisverbruik als P1 + omvormer, zoals in de ontwerpregels |
| EV-vermogen (optioneel) | `sensor.charge_amps_monitor_charger_current_power` | wordt van het basisverbruik afgetrokken |
| Prijscurve (optioneel) | `sensor.energy_prices_electricity_import_price` | terugval als Nord Pool uitvalt en controle op de eigen prijsberekening; moet een `price_curve`-attribuut hebben (`start`, `end`, `price`) |

4. Instellingen, HEMS, Configureren: de standaardwaarden zijn de besluiten uit `docs/hems/intake-decisions.md` (capaciteit 25 kWh, 8 kW, vloer 5 %, reserve 30 %, round trip 0,82, minimale winstmarge 0,10, wachtkosten 0,002, prijscomponenten zoals energy-prices, Nord Pool aan voor zone NL). PV-factor 0 betekent automatisch kalibreren op de opgenomen PV. Het piekvermogen PV (standaard 5000 W: de panelen haalden deze week maximaal 4964 W, de omvormer kan 8 kW) kapt de PV-verwachting af; staat het te hoog, dan voorspelt HEMS op zonnige dagen meer PV dan de panelen kunnen leveren.

## Wat je ziet

Na een herstart van Home Assistant staan de sensoren van battery-api er nog niet meteen; HEMS meldt dan kort `no_soc` en plant na 60 seconden zelf opnieuw.

Alle sensoren hangen onder één apparaat "HEMS". Vermogens volgen de HEMS-conventie: **plus = laden, min = ontladen**.

| Sensor | Betekenis |
|---|---|
| `sensor.hems_battery_action` | charge, discharge of idle voor het huidige kwartier; attributen `reason` en `keep_value_eur_kwh` leggen uit waarom |
| `sensor.hems_battery_setpoint` | vermogen in W dat de uitvoerder nu zou sturen, na controle op de actuele SoC; attributen `planned_w`, `overridden`, `reason` |
| `sensor.hems_executor` | `as_planned`, `at_floor`, `limited_floor`, `at_full`, `limited_full`, `no_soc`, `stale_soc`, `expired` of `no_plan`: wat de uitvoerder met de opdracht van de planner deed |
| `sensor.hems_expected_saving` | verwachte besparing over de horizon (EUR kas; de minimale winstmarge telt niet als kost mee) |
| `sensor.hems_status` | ok, no_soc, stale_soc, no_prices of no_price_for_now; attribuut `price_source` (market of curve) |
| `binary_sensor.hems_tomorrow_prices_available` | aan zodra (een deel van) de prijzen van morgen bekend zijn; attributen `tomorrow_intervals`, `prices_until`, `price_source` |
| `sensor.hems_import_price`, `sensor.hems_export_price` | prijs van het huidige kwartier; export met bonus alleen overdag en bij positieve prijs; attribuut `curve` met alle bekende prijzen vanaf nu (`start` in lokale tijd, `price` in EUR/kWh), dus morgen erbij zodra Nord Pool die publiceert |
| `sensor.hems_pv_forecast_next_hour` | PV-opbrengst van het komende uur (kWh) zoals het plan die gebruikt; attribuut `forecast` met de komende 24 uur per kwartier |
| `sensor.hems_load_forecast_next_hour` | verwacht huisverbruik komend uur (kWh, zonder EV); attribuut `forecast` per kwartier |
| `sensor.hems_irradiance_forecast`, `sensor.hems_temperature_forecast` | gemiddelde zoninstraling (W/m²) en buitentemperatuur (°C) van het komende uur uit Open-Meteo; attribuut `forecast` per kwartier. Onbekend zolang het weer niet binnen is of uit staat |
| `sensor.hems_sell_window` | begin van het volgende verkoopvenster (tijdstip; waar het plan verkoopt, anders het begin van de band). Een venster is een stuk van de horizon waar verkopen méér oplevert dan het goedkoopste laadmoment ervoor (vers laden) of erna (terugkopen) kost, plus de marge. Attributen `windows` (per venster: `from`, `to`, `peak`, `viable` = both/fresh/replace, `need_fresh`/`room_fresh` en `need_replace`/`room_replace` = de drempel en wat de piek erboven of eronder zit, `status`, `sold_kwh`, `sold_from`/`sold_to`, `from_stock_kwh` en `charges` = de laadmomenten waaruit het verkocht wordt), `status`, `outside_kwh` (verkocht buiten elk venster). Een vers laadmoment mag ook een van het laatste etmaal vóór de horizon zijn (de voorraad van het middagladen telt dus nog mee bij de avondverkoop). Status: `planned` (het beste kwartier wordt verkocht), `partial`, `no_stock` (niets boven de vloer en geen laadmoment dat nog bruikbaar is en loont: een laadmoment van vóór het moment dat de batterij leeg raakte telt niet meer; `room_usable` is de ruimte op het bruikbare laadmoment), `kept_for_later` (energie wacht op een duurder venster), `unsold` (er is energie of een bruikbaar laadmoment dat loont, en er wordt niets verkocht: een bevinding). Een verkoop onder 0,5 kWh telt als niet verkocht, zodat 0,4 kWh boven de vloer het venster niet laat flippen. Het beslist niets; het plan blijft van de planner |
| `sensor.hems_charge_window`, `sensor.hems_discharge_window` | begin van de eerste laad- of ontlaadperiode van het plan (tijdstip, Home Assistant toont het als "over 2 uur"). Een periode loopt van het eerste kwartier tot het laatste kwartier vóór de tegenovergestelde actie, ook als het plan er een rustkwartier tussen laat vallen; een rust van meer dan een uur begint een nieuwe periode (nachtlading en middagbijlading blijven twee periodes). De zin en de tabel van `sensor.hems_plan` volgen dezelfde indeling. Attributen: `end`, `kwh` (totaal), `power_w` (gemiddeld over de kwartieren die echt laden of ontladen), `avg_price_eur_kwh` (gewogen op energie), `soc_from_pct`, `soc_to_pct`, en `pv_kwh` en `load_kwh` die in de hele periode verwacht worden. Onbekend als het plan zo'n periode niet heeft; loopt de periode al, dan is het begin het huidige kwartier |
| `sensor.hems_pv_forecast_24h` | PV-verwachting komende 24 uur (kWh) |
| `sensor.hems_plan` | het plan als zin, in de taal van Home Assistant en lokale tijd: `Laden 10:45–13:15 · Ontladen 15:45–18:15 · Laden morgen 00:45–03:45`; attributen `markdown` (het plan als tabel voor een dashboardkaart, zie hieronder), `windows` (dezelfde vensters met kWh, vermogen, SoC en gemiddelde prijs), `quarters` (aantal geplande kwartieren) en `slots` (de komende 12 uur per kwartier met `start`, `action`, `power_w`, `soc_kwh`, `reason`) |

### Plan als tabel op een dashboard

`sensor.hems_plan` heeft het attribuut `markdown`: het plan als tabel, in de taal van Home Assistant en lokale tijd. De eerste rij is wat er nu gebeurt (🔴, ook bij rust), daarna volgen de komende laad- en ontlaadvensters (⏰) met gemiddeld vermogen, gemiddelde prijs, de SoC aan begin en einde en het doel: bij laden voor welke verkoop (`voor verkoop 17:15–19:30`), bij ontladen welke piek (`piek 0.489`, `(uit voorraad)` als de energie al in de batterij zat). Een venster van morgen noemt de dag. Toon het met een Markdown-kaart:

```yaml
type: markdown
title: HEMS-plan
content: |
  Nu: {{ states('sensor.hems_battery_action') }} · import €{{ states('sensor.hems_import_price') }}/kWh · verwachte besparing €{{ states('sensor.hems_expected_saving') }}

  {{ state_attr('sensor.hems_plan', 'markdown') }}
```

### Prijzen en verwachting als grafiek

De reeksen staan in attributen (`curve`, `forecast`) en worden niet in de recorder bewaard (ze veranderen elk kwartier en zouden de database vullen). Voor een grafiek kun je de aangepaste kaart ApexCharts (via HACS) gebruiken:

```yaml
type: custom:apexcharts-card
header: {show: true, title: Prijzen en PV}
graph_span: 24h
span: {start: hour}
yaxis:
  - id: price
    decimals: 2
  - id: kwh
    opposite: true
    decimals: 2
series:
  - entity: sensor.hems_import_price
    name: Import
    yaxis_id: price
    type: line
    data_generator: |
      return entity.attributes.curve.map(p => [new Date(p.start).getTime(), p.price]);
  - entity: sensor.hems_export_price
    name: Export
    yaxis_id: price
    type: line
    data_generator: |
      return entity.attributes.curve.map(p => [new Date(p.start).getTime(), p.price]);
  - entity: sensor.hems_pv_forecast_next_hour
    name: PV per kwartier
    yaxis_id: kwh
    type: area
    data_generator: |
      return entity.attributes.forecast.map(p => [new Date(p.start).getTime(), p.kwh]);
```

Zonder aangepaste kaart toont een Markdown-kaart de eerste vensters: `{{ states('sensor.hems_charge_window') }}` en de attributen erbij.

## Logging: alle beslissingen en de hele plan-boom

HEMS schrijft in `/config/hems/` drie bestanden, elk met roterende generaties (`.1`, `.2`). Samen laten ze zien wat er besloten is, waarom, en hoe het hele plan er op dat moment uitzag.

| Bestand | Inhoud | Omvang |
|---|---|---|
| `decision_trace.jsonl` | Eén regel per kwartier: status, invoer met leeftijden (SoC, prijzen, weer, historie), de vergelijking achter de actie (`compare`: verkoopwaarde, bewaarwaarde, kopen, drempel/vol-vlaggen, beste latere verkoop en aankoop met tijdstip), `segments` (het hele plan als aaneengesloten runs laden/ontladen/rust met vermogen, kWh, prijs en SoC), vorige actie en `plan_shift` | ca. 3 KB per kwartier, 20 MB per generatie, 3 generaties |
| `plans.jsonl` | Eén regel per kwartier met elk geplande kwartier als compacte arrays: actie, redencode, vermogen, SoC, net, bewaar-/verkoop-/koopwaarde, import- en exportprijs, verbruik en PV. Daarmee is elk plan achteraf te reconstrueren en te vergelijken | ca. 1 MB per dag, 30 MB per generatie, 2 generaties; uit te zetten met "volledig plan loggen" in de opties |
| `events.jsonl` | Gebeurtenissen: `settings` (instellingen, hash, gekozen entiteiten), `history`, `market` (per dag HTTP-status en aantal kwartieren, tot wanneer bekend), `weather`, `pv_gain`, `status` (van, naar), `action` (van, naar, reden), `windows` (de verkoopvensters en hun status, alleen als die verandert), `retry` (na een herstart zonder SoC of prijzen, of na een mislukte weer-fetch zonder eerdere kopie: één snelle herhaling na 60 s per storing, daarna weer om de 30 minuten) | klein |

Redencodes in `plans.jsonl`: `s` verkopen loont meer dan bewaren, `b` kopen is goedkoper dan bewaren, `h` vasthouden, `f` vasthouden op de reservevloer (verkopen zou lonen maar mag niet lager), `v` vasthouden omdat de batterij vol is. Alle waarden zijn EUR per kWh in de batterij; `keep` is wat de rest van de horizon die kWh waard is.

### Verkoopvensters in het log en in de reader

Bij elk kwartier staat onder de plan-boom een blok `HEMS sell windows`: per venster waar het verkocht wordt, de piek, wat het nodig heeft op beide grondslagen (`after a charge at 04:15 needs 0.514 (-0.025)`, `bought back at 14:00 needs 0.382 (+0.107)`) en wat het plan ermee doet. `python3 scripts/hems_trace.py windows [TIME]` toont dat voor één kwartier en daarna per venster de statussen die het doorliep (`no_stock -> planned`): een venster dat tussen kwartieren heen en weer springt is een plan dat niet houdt. Een `unsold` venster of verkoop buiten elk venster geeft één WARNING (`HEMS window check`) per verandering, niet per kwartier.

### Boiler in de belastingverwachting

De warmwater-warmtepomp is de grootste last die niet elke dag op hetzelfde uur draait: de water-heater-add-on (vanaf 1.3.0) verwarmt in het goedkoopste venster van de dag en publiceert zijn plan als `sensor.wh_heating_plan` (attribuut `windows`: soort, start, einde, verwacht kWh; attribuut `heating_energy_kwh`). HEMS leest alleen die entity (optie "Entiteit met het plan van de boiler", standaard `sensor.wh_heating_plan`, leeg = uit): per dag gaat de boiler uit de historie (het piekuur van de dag verliest zijn overschot boven de mediaan, hooguit `heating_energy_kwh`) en de geplande runs komen terug op het uur dat de module opgeeft, gelijk verdeeld over de kwartieren. Zonder entity (add-on nog niet bijgewerkt, entity niet beschikbaar) verandert er niets. In het spoor staat `inputs.heating_runs` en `load_source` is `history+heater`.

Achtergrond (16 okt 2026): op acht opgenomen dagen was er elke dag één uur met 1,7 tot 3,4 kWh boven de mediaan rond het middaguur, steeds 1 tot 2 uur vóór het goedkoopste uur. De oorzaak lag bij de add-on: die haalde de tijdzone van de UTC-prijscurve er alleen af (`replace(tzinfo=None)`) in plaats van om te rekenen, waardoor het venster in zomertijd twee uur te vroeg lag. Dat is in 1.3.0 hersteld; na de update schuift de boiler naar het echt goedkoopste uur.

### Terugkijken met de replay

`python3 scripts/hems_replay.py --from 2026-10-15 --to 2026-10-16 [--write docs/hems/observations/replay-2026-10-15.md]` speelt de planner over opgenomen dagen na en vergelijkt het kasresultaat met wat de echte batterij deed. Prijzen komen uit de recorder-export (tot 12 okt) en voor latere dagen uit `plans.jsonl` (eerst `hems_trace.py --pull`); de uurgemiddelden komen uit `hems_collect.py run --hours 72`. Ontbreekt een van beide, dan zegt het script welke opdracht nodig is. De replay kent belasting en PV vooraf (oracle) en spreidt uurgemiddelden over vier kwartieren: hij toont wat de planner op die prijzen kan, niet wat de prognoses ervan maken.

### Welke code maakte deze regel? (build)

`hems/deploy.py` schrijft de commit van de uitgerolde code naar `custom_components/hems/BUILD` (`abc1234`, met `+dirty` als er niet-gecommitte wijzigingen in `custom_components/hems` of `hems/core` zaten). HEMS zet die in elk beslissingsrecord (`build` in `decision_trace.jsonl`), in de `settings`-gebeurtenis, in het HA-log (`HEMS build abc1234` bij het opstarten) en als softwareversie van het apparaat. Een review die een regel in twijfel trekt kijkt eerst naar `build`: een regel van vóór de fix is geen open bug. Zonder BUILD (met de hand gekopieerd) staat er `unknown`.

### Planner en uitvoerder

De **planner** bepaalt elk kwartier uit prijzen en voorspellingen hoe de dag eruitziet: laden in het goedkope venster, verkopen uit de geladen energie later. Hij plant vanaf de werkelijke SoC en maakt zichzelf elk kwartier opnieuw. De **uitvoerder** is de laatste controle vóór een apparaat: hij leest de actuele SoC opnieuw, bij elke SoC-update binnen het kwartier, en laat de opdracht nooit onder de vloer (reserve of harde minimum) ontladen, boven vol laden, of draaien op een SoC die ontbreekt of niet meer ververst wordt. Ontbreekt er nog maar een beetje ruimte, dan vertraagt hij het vermogen zodat het kwartier precies op de vloer eindigt. Dat staat in `sensor.hems_executor`, in `events.jsonl` (`executor`) en als WARNING in het HA-log zodra hij het plan overschrijft. Zodra HEMS naar de batterij gaat schrijven, gebeurt dat uitsluitend via de uitvoerder.

De uitvoerder rekent de ruimte tot vol of tot de vloer vanaf het moment dat de SoC-waarde voor het laatst **veranderde** (`Reading.changed_at`, bij Home Assistant `last_changed`), niet vanaf het moment van de laatste melding. Een sensor die elke minuut hetzelfde getal herhaalt terwijl de batterij laadt, liet anders de limiet met de klok meestijgen en dan weer instorten (14 okt 15:00, `limited_full` en `as_planned` om de halve minuut). De limiet verandert nu alleen mee met een nieuwe SoC-waarde.

### Wachtkosten

De planner rekent vasthouden standaard als gratis. Bij gelijke prijzen laadt hij dan zo vroeg mogelijk, ook al is de verkoop pas 16 uur later. De instelling "Wachtkosten" (EUR per opgeslagen kWh per uur, standaard 0,002; 0 = uit) laat hem bij gelijke prijzen pas vlak voor de verkoop laden, vergelijkbaar met de sell buffer van battery-manager (buffer pas enkele uren vóór de verkoop laden). De werkelijke stilstandsverliezen van de batterij zijn klein (gemeten: ca. 0,1 % SoC per uur, 10 okt), het gaat dus om beslisruimte en onzekerheid, niet om verlies. Replay 4-11 okt (kas, bekend verbruik en PV): uit € 16,76, 0,001 € 16,94, **0,002 € 18,15**, 0,003 € 17,98, 0,005 € 17,25, 0,008 € 14,33. Per dag is het gemengd: op de dag met de grootste spread (6 okt) kost 0,002 € 1,24 (5,78 naar 4,54), omdat de goedkoopste uren dan minder volledig benut worden; op de andere dagen wint het meer. Op het live plan van 13 okt (36 uur, één keer plannen) kost 0,002 € 0,40 van € 7,11 en laadt het pas rond 00:00 in plaats van vanaf 13:45.

### Logging in Home Assistant

HEMS zet zijn eigen logger bij het starten op INFO, tenzij je in `configuration.yaml` zelf een niveau voor `custom_components.hems` instelt (Home Assistant staat standaard op `logger: default: warning`, waardoor INFO-regels van een eigen integratie anders onzichtbaar blijven). Per kwartier komen er twee regels in het HA-log:

```text
HEMS 13:45 ok: charge 7730 W | soc 46.6% | sell 0.1473 keep 0.2968 buy 0.2901 -> buy; best sell later +1d 09:00 @0.4715 | import 0.2627 export 0.2758 | 137 quarters, prices market | expected saving 7.106 EUR
HEMS plan from 13:45, 137 quarters, expected saving 7.106 EUR:
  charge    13:45 - 15:00   7730 W    9.7 kWh  soc 47% -> 82%  @0.2621
  discharge +1d 07:30 - +1d 09:45   7043 W   15.8 kWh  soc 100% -> 30%  @0.516
```

Je ziet ze in Instellingen, Systeem, Logs (zoek op "HEMS"), of met `python3 scripts/hems_trace.py halog`. Tijden zijn lokaal; `+1d` betekent: morgen. Elk event uit `events.jsonl` staat ook als regel `HEMS event <naam> ...` in het log, en een status anders dan `ok` of een ingreep van de uitvoerder als WARNING. De leestool toont dezelfde dagaanduiding.

Lezen met de leestool (haalt de bestanden met de SSH-sleutel van de server):

```bash
python3 scripts/hems_trace.py --pull tail -n 20      # een regel per kwartier
python3 scripts/hems_trace.py show 16:15             # dat kwartier in het geheel: invoer, vergelijking, segmenten, elk geplande kwartier
python3 scripts/hems_trace.py why 18:30              # waarom het plan om 18:30 doet wat het doet (vandaag; 'YYYY-MM-DD HH:MM' voor een andere dag)
python3 scripts/hems_trace.py diff 15:00 15:15       # welke kwartieren het nieuwe plan anders plant dan het vorige
python3 scripts/hems_trace.py events --type market   # Nord Pool-ophaalacties
```

## Beoordelen

Vergelijk `sensor.hems_battery_setpoint` met het werkelijke batterijvermogen en met de acties van battery-manager. De replay op 4-11 okt (`docs/hems/observations/replay-2026-10-13.md`) is het referentiepunt, maar die gebruikt bekend verbruik en bekende PV; de dry-run laat zien hoeveel de echte voorspellingen kosten.

## Terugdraaien

Integratie verwijderen onder Apparaten en diensten, map `custom_components/hems/` en `/config/hems/` weghalen. Er is niets anders gewijzigd. Het deploy-script bewaart de laatste drie versies als `/config/.hems-backup/hems-*.tar.gz`.

## Bekende beperkingen

- Alleen dry-run; schrijven naar de batterij is er niet.
- PV-voorspelling is grof: één factor op Open-Meteo-straling (R² 0,82 op 3-12 okt). Weer komt van `api.open-meteo.com` (blijft aan, besluit van Mark); uitzetten kan in de opties; zonder weer is de PV-verwachting 0 en staat dat in de trace.
- Verbruiksvoorspelling: mediaan per lokaal uur over 7 dagen uit de recorder-statistieken; tot er historie is geldt 400 W.
- Prijzen haalt HEMS zelf op bij Nord Pool (`dataportal-api.nordpoolgroup.com`, dezelfde bron als energy-prices; morgen verschijnt rond 13:00, tot dan antwoordt de API 204). Valt Nord Pool uit, dan gebruikt HEMS de `price_curve`-sensor; het verschil tussen beide staat in de trace als `price_check_max_diff` (hoort rond 0,0001 te liggen, meer wijst op andere prijsinstellingen dan energy-prices). Zonder beide bronnen is de status `no_prices`.
- Uitgaand verkeer: alleen `dataportal-api.nordpoolgroup.com` en `api.open-meteo.com` (die laatste met op 0,01° afgeronde coördinaten).
- Of de Zonnebonus ook voor avondlevering uit de batterij geldt is onbevestigd; de schakelaars in de opties dekken beide.

## Ontwikkelen

```bash
# kern (geen HA nodig)
cd hems/core && python3 -m pytest
# na elke wijziging in hems/core: engine-kopie in de integratie bijwerken
python3 scripts/sync_hems_core.py
# integratietests (eigen venv met exact de serverversie van HA)
python3 -m venv .venv-ha && .venv-ha/bin/pip install "pytest-homeassistant-custom-component==0.13.367"
.venv-ha/bin/python -m pytest tests/hems_ha
# replay op de lokale data
python3 scripts/hems_replay.py --write docs/hems/observations/replay.md
```
