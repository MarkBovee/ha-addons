<p align="center"><img src="../custom_components/hems/brand/logo@2x.png" alt="HEMS" height="96"></p>

# HEMS: home energy management for Home Assistant

HEMS plans when your home battery charges and sells, when the water heater runs and when the car charges, from the quarter-hour
day-ahead prices, your solar forecast and your house's own load history. It is a Home Assistant custom integration with its own
sidebar panel.

HEMS talks to your devices through Home Assistant entities and services only. It does not care which integration a battery,
charger or water heater comes from, as long as Home Assistant exposes the readings and the controls.

> **Status: dry run and advisory.** HEMS plans and shows what it would do. Writing to devices is built and tested but locked:
> nothing is sent to a battery, water heater or charger until you open that lock yourself, module by module.

## What it does

- **Battery.** A dynamic-programming planner over the coming 24–48 hours, per quarter: charge when power is cheap, sell at the
  peaks, and cover the house in between (self-consumption, 0 W at the meter). Sales stop at a sell floor that follows the
  expected use until the battery can refill (30–60 % by default), so a cold night keeps more in reserve.
- **SAJ time slots.** For SAJ hybrid inverters (`saj_h2_modbus`), the plan becomes the inverter's daily time slots, with short
  pauses merged when that costs little, plus an own grid-follow that keeps the meter at 0 W. Shown as "Would write" until
  unlocked.
- **Water heater.** The cheapest day run, the weekly legionella run (only when it is due, counted in calendar days), and the
  target temperature per program: night preheat, day run, bath, away, negative price, stand-by. Every temperature is a setting.
- **EV charging.** A charging plan against departure deadlines, a price threshold and solar surplus, limited per phase by the
  grid connection.
- **Prices.** Nord Pool day-ahead prices per quarter with your tariff (VAT, markup, energy tax, net metering until a date).
- **Insights.** What the battery really did against plain self-consumption, per day, week, month and year, the rest-of-day
  forecast, and how far the solar and load forecasts were off.
- **Energy dashboard.** kWh counters for solar and battery in and out, and one action that adds them and HEMS's prices to Home
  Assistant's Energy dashboard where they are missing.

## Requirements

- Home Assistant 2026.3 or later (tested on 2026.10.4).
- Entities for the battery state of charge, battery power, solar power and grid power. Optional: inverter output, EV charger
  (power, plugged, charging, current per phase, limit), the car's state of charge, meter current per phase, water heater, away
  and bath toggles.

## Installation

HEMS is not in HACS yet. Install it by hand:

1. Copy `custom_components/hems/` into `/config/custom_components/hems/` on your Home Assistant.
2. Restart Home Assistant.
3. Settings → Devices & services → Add integration → **HEMS**, and pick your entities.
4. Open **HEMS** in the sidebar. The gear holds the settings, the mode per module and the Energy dashboard setup.

## Safety

- Every module starts in **dry run**. **Advisory** shows what it would do. **Auto** (writing) cannot be chosen yet.
- A master switch is off after every restart.
- HEMS never writes on stale or missing data, nor in the first cycle after a start.
- The SAJ writer writes only what differs, verifies by reading back, and retries what the inverter did not take.
- A watchdog automation (`hems/watchdog/hems_saj_watchdog.yaml`) clears the inverter's slots when HEMS stops working while it
  controls the battery.

## Entities and services

HEMS creates one service device, **HEMS**, with sensors for the plan, prices, forecasts, the realised result, the advisory
battery schedule and water heater target, alerts, and a mode select per module. Services:

| Service | What it does |
|---|---|
| `hems.setup_energy_dashboard` | Adds HEMS's solar, battery and prices to the Energy dashboard where missing (`preview: true` to see first) |
| `hems.apply_recommendation`, `hems.dismiss_recommendation` | Act on an advisory recommendation |
| `hems.disarm_all` | Every module back to dry run |

## Development

The engine (`hems/core`) is plain Python without Home Assistant; `custom_components/hems/engine/` is a generated copy of it
(`python3 scripts/sync_hems_core.py`). Tests:

```bash
cd hems/core && python -m pytest -q -p no:homeassistant -p no:pytest_homeassistant_custom_component
python -m pytest tests/hems_ha -q          # with pytest-homeassistant-custom-component 0.13.375
```

Brand images are rendered from `docs/hems/brand/*.svg` with `scripts/build_hems_brand.sh`. Design notes and plans (in Dutch)
live in `docs/hems/`; `hems/AGENTS.md` has the working rules for contributors and coding agents.

## License

MIT, see [LICENSE](../LICENSE).
