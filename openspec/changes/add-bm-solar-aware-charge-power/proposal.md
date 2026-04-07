## Why
Battery Manager gebruikt nu alleen realtime solar-surplus voor Passive Solar en houdt bij geplande laadvensters geen rekening met de verwachte resterende zonne-energie van vandaag. Daardoor vraagt het systeem tijdens goedkope laadperioden vaak te veel netlaadvermogen, terwijl de battery API het gevraagde vermogen bovenop actuele PV-productie optelt.

## What Changes
- Add solar-aware charge power allocation voor geplande charge windows van vandaag.
- Add ondersteuning voor `sensor.energy_production_today_remaining` als resterende solar-energiebudget voor de rest van de dag.
- Add rolling hourly herberekening van charge power op basis van actuele SOC, resterende charge slots en resterende solar-forecast.
- Add configuratie voor enable/disable, safety factor en minimum commanded charge power.
- Keep fallback naar huidig gedrag wanneer forecast-data ontbreekt of ongeldig is.

## Impact
- Affected specs: `battery-strategy`
- Affected code:
  - `battery-manager/app/main.py`
  - `battery-manager/app/solar_charge_optimizer.py`
  - `battery-manager/config.yaml`
  - `battery-manager/README.md`
  - `battery-manager/CHANGELOG.md`
  - `battery-manager/Tests/test_main_reduced_adaptive.py`
  - `battery-manager/Tests/test_solar_charge_optimizer.py`