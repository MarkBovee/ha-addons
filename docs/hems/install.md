# HEMS dry-run installeren op Home Assistant

HEMS v0.1 plant elk kwartier wat de batterij zou moeten doen, publiceert dat als sensoren en schrijft per kwartier één regel in een trace. Het **schrijft nooit naar een apparaat**: battery-manager en battery-api blijven de batterij sturen. Doel: een paar dagen naast de bestaande sturing draaien en vergelijken.

Getest tegen Home Assistant 2026.9.4 (de versie op de server) met `pytest-homeassistant-custom-component` 0.13.367.

## Installeren

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
| Prijscurve | `sensor.energy_prices_electricity_import_price` | moet een `price_curve`-attribuut hebben (`start`, `end`, `price`) |

4. Instellingen, HEMS, Configureren: de standaardwaarden zijn de besluiten uit `docs/hems/intake-decisions.md` (capaciteit 25 kWh, 8 kW, vloer 5 %, reserve 30 %, round trip 0,82, slijtagemarge 0,10, prijscomponenten zoals energy-prices). PV-factor 0 betekent automatisch kalibreren op de opgenomen PV.

## Wat je ziet

Alle sensoren hangen onder één apparaat "HEMS". Vermogens volgen de HEMS-conventie: **plus = laden, min = ontladen**.

| Sensor | Betekenis |
|---|---|
| `sensor.hems_battery_action` | charge, discharge of idle voor het huidige kwartier; attributen `reason` en `keep_value_eur_kwh` leggen uit waarom |
| `sensor.hems_battery_setpoint` | vermogen in W dat HEMS nu zou vragen |
| `sensor.hems_expected_saving` | verwachte besparing over de horizon (EUR, zonder slijtage) |
| `sensor.hems_status` | ok, no_soc, stale_soc, no_prices of no_price_for_now |
| `sensor.hems_import_price`, `sensor.hems_export_price` | prijs van het huidige kwartier; export met bonus alleen overdag en bij positieve prijs |
| `sensor.hems_pv_forecast_next_24_h` | PV-verwachting komende 24 uur (kWh) |
| `sensor.hems_plan` | aantal geplande kwartieren; attribuut `slots` met de komende 12 uur |

## Decision trace

`/config/hems/decision_trace.jsonl`: een regel per kwartier met tijdstip, SoC, prijzen, actie, vermogen, reden (`sell 0.31 > keep 0.27`: verkoopwaarde per opgeslagen kWh tegenover de waarde van bewaren), aantal kwartieren zonder verbruiks- of PV-voorspelling, en `plan_shift` wanneer het plan voor een kwartier meer dan 25 % verschoof. Roteert bij 20 MB.

```bash
tail -n 4 /config/hems/decision_trace.jsonl | jq '{ts, status, action: .first_action, power_w, reason}'
```

## Beoordelen

Vergelijk `sensor.hems_battery_setpoint` met het werkelijke batterijvermogen en met de acties van battery-manager. De replay op 4-11 okt (`docs/hems/observations/replay-2026-10-13.md`) is het referentiepunt, maar die gebruikt bekend verbruik en bekende PV; de dry-run laat zien hoeveel de echte voorspellingen kosten.

## Terugdraaien

Integratie verwijderen onder Apparaten en diensten, map `custom_components/hems/` en `/config/hems/` weghalen. Er is niets anders gewijzigd.

## Bekende beperkingen

- Alleen dry-run; schrijven naar de batterij is er niet.
- PV-voorspelling is grof: één factor op Open-Meteo-straling (R² 0,82 op 3-12 okt). Weer komt van `api.open-meteo.com`; alleen de op 0,01° afgeronde locatie verlaat de installatie. Uitzetten kan in de opties; zonder weer is de PV-verwachting 0 en staat dat in de trace.
- Verbruiksvoorspelling: mediaan per lokaal uur over 7 dagen uit de recorder-statistieken; tot er historie is geldt 400 W.
- Prijzen komen uit de `price_curve` van de energy-prices-sensor; HEMS haalt Nord Pool nog niet zelf op.
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
