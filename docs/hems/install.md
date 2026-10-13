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

4. Instellingen, HEMS, Configureren: de standaardwaarden zijn de besluiten uit `docs/hems/intake-decisions.md` (capaciteit 25 kWh, 8 kW, vloer 5 %, reserve 30 %, round trip 0,82, minimale winstmarge 0,10, prijscomponenten zoals energy-prices, Nord Pool aan voor zone NL). PV-factor 0 betekent automatisch kalibreren op de opgenomen PV.

## Wat je ziet

Na een herstart van Home Assistant staan de sensoren van battery-api er nog niet meteen; HEMS meldt dan kort `no_soc` en plant na 60 seconden zelf opnieuw.

Alle sensoren hangen onder één apparaat "HEMS". Vermogens volgen de HEMS-conventie: **plus = laden, min = ontladen**.

| Sensor | Betekenis |
|---|---|
| `sensor.hems_battery_action` | charge, discharge of idle voor het huidige kwartier; attributen `reason` en `keep_value_eur_kwh` leggen uit waarom |
| `sensor.hems_battery_setpoint` | vermogen in W dat HEMS nu zou vragen |
| `sensor.hems_expected_saving` | verwachte besparing over de horizon (EUR kas; de minimale winstmarge telt niet als kost mee) |
| `sensor.hems_status` | ok, no_soc, stale_soc, no_prices of no_price_for_now; attribuut `price_source` (market of curve) |
| `binary_sensor.hems_tomorrow_prices_available` | aan zodra (een deel van) de prijzen van morgen bekend zijn; attributen `tomorrow_intervals`, `prices_until`, `price_source` |
| `sensor.hems_import_price`, `sensor.hems_export_price` | prijs van het huidige kwartier; export met bonus alleen overdag en bij positieve prijs |
| `sensor.hems_pv_forecast_24h` | PV-verwachting komende 24 uur (kWh) |
| `sensor.hems_plan` | aantal geplande kwartieren; attribuut `slots` met de komende 12 uur |

## Logging: alle beslissingen en de hele plan-boom

HEMS schrijft in `/config/hems/` drie bestanden, elk met roterende generaties (`.1`, `.2`). Samen laten ze zien wat er besloten is, waarom, en hoe het hele plan er op dat moment uitzag.

| Bestand | Inhoud | Omvang |
|---|---|---|
| `decision_trace.jsonl` | Eén regel per kwartier: status, invoer met leeftijden (SoC, prijzen, weer, historie), de vergelijking achter de actie (`compare`: verkoopwaarde, bewaarwaarde, kopen, drempel/vol-vlaggen, beste latere verkoop en aankoop met tijdstip), `segments` (het hele plan als aaneengesloten runs laden/ontladen/rust met vermogen, kWh, prijs en SoC), vorige actie en `plan_shift` | ca. 3 KB per kwartier, 20 MB per generatie, 3 generaties |
| `plans.jsonl` | Eén regel per kwartier met elk geplande kwartier als compacte arrays: actie, redencode, vermogen, SoC, net, bewaar-/verkoop-/koopwaarde, import- en exportprijs, verbruik en PV. Daarmee is elk plan achteraf te reconstrueren en te vergelijken | ca. 1 MB per dag, 30 MB per generatie, 2 generaties; uit te zetten met "volledig plan loggen" in de opties |
| `events.jsonl` | Gebeurtenissen: `settings` (instellingen, hash, gekozen entiteiten), `history`, `market` (per dag HTTP-status en aantal kwartieren, tot wanneer bekend), `weather`, `pv_gain`, `status` (van, naar), `action` (van, naar, reden), `retry` | klein |

Redencodes in `plans.jsonl`: `s` verkopen loont meer dan bewaren, `b` kopen is goedkoper dan bewaren, `h` vasthouden, `f` vasthouden op de reservevloer (verkopen zou lonen maar mag niet lager), `v` vasthouden omdat de batterij vol is. Alle waarden zijn EUR per kWh in de batterij; `keep` is wat de rest van de horizon die kWh waard is.

Daarnaast schrijft HEMS per kwartier één regel in het Home Assistant-log (`custom_components.hems`, niveau INFO).

Lezen met de leestool (haalt de bestanden met de SSH-sleutel van de server):

```bash
python3 scripts/hems_trace.py --pull tail -n 20      # een regel per kwartier
python3 scripts/hems_trace.py show 16:15             # dat kwartier in het geheel: invoer, vergelijking, segmenten, elk geplande kwartier
python3 scripts/hems_trace.py why 18:30              # waarom het plan om 18:30 doet wat het doet
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
