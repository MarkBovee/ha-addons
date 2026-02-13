# Battery Manager

Optimize battery charging and discharging using dynamic electricity prices, solar surplus, grid export detection, and EV charging awareness.

## Overview

Battery Manager generates rolling charge/discharge schedules based on price curves from the Energy Prices add-on. It classifies prices into four ranges — **load** (cheapest, charge battery), **discharge** (most expensive, sell), **adaptive** (mid-range, discharge to 0W grid), and **passive** (below threshold, battery idle) — adjusts discharge power in real time, and applies SOC protection, grid export prevention, solar surplus, and EV charging rules.

## Prerequisites

- Home Assistant Supervisor
- Mosquitto MQTT broker add-on
- Energy Prices add-on (price curve sensor)
- Battery API add-on (MQTT schedule topic)

## Installation

1. Install this repository in Home Assistant Add-on Store.
2. Install **Energy Prices** and **Battery API** add-ons first.
3. Install **Battery Manager** add-on.
4. Configure options in the add-on UI.
5. Start the add-on.

## Configuration

Key options (defaults in config.yaml):

- **timing.update_interval**: schedule refresh interval (seconds)
- **timing.monitor_interval**: real-time monitoring interval (seconds)
- **timing.adaptive_power_grace_seconds**: minimum seconds between adaptive power changes
- **timing.schedule_regen_cooldown_seconds**: cooldown for rolling schedule regeneration
- **dry_run**: log schedules without publishing to MQTT
- **entities.price_curve_entity**: price curve sensor entity
- **entities.export_price_curve_entity**: export price curve sensor entity
- **entities.soc_entity**: battery SOC sensor
- **entities.grid_power_entity**: grid power sensor (import/export)
- **entities.solar_power_entity**: solar production sensor
- **entities.house_load_entity**: house load sensor
- **entities.temperature_entity**: outdoor temperature sensor
- **power.max_charge_power**: maximum charge power (W)
- **power.max_discharge_power**: maximum discharge power (W)
- **power.min_discharge_power**: baseline discharge power for adaptive periods (W)
- **power.min_scaled_power**: minimum scaled power for ranked charge/discharge (W)
- **soc.min_soc**: hard minimum SOC (%)
- **soc.conservative_soc**: conservative SOC threshold (%)
- **soc.target_eod_soc**: end-of-day target SOC (%)
- **soc.max_soc**: max SOC allowed for charging
- **heuristics.top_x_charge_hours**: cheapest periods to charge
- **heuristics.top_x_discharge_hours**: most expensive periods to discharge
- **passive_solar.enabled**: enable 0W charge gap on excess solar
- **passive_solar.entry_threshold**: grid export threshold to enter passive mode (W, default 1000)
- **passive_solar.exit_threshold**: grid import threshold to exit passive mode (W, default 200)
- **heuristics.charging_price_threshold**: price below which battery stays idle (passive range, EUR/kWh)
- **heuristics.min_profit_threshold**: minimum spread between load and discharge prices (EUR/kWh)
- **heuristics.overnight_wait_threshold**: evening vs overnight price gap to wait for cheaper charging (EUR/kWh)
- **temperature_based_discharge.enabled**: enable temperature mapping
- **temperature_based_discharge.thresholds**: temperature → discharge hours mapping
- **ev_charger.enabled**: enable EV charger integration
- **ev_charger.charging_threshold**: EV charging threshold (W)
- **ev_charger.entity_id**: EV charger power sensor

## MQTT Entities

The add-on publishes status entities via MQTT Discovery under the **Battery Manager** device:

| Entity | Purpose |
|--------|---------|
| `sensor.bm_status` | Current operational state (Charging, Discharging, Idle, Paused, Reduced) |
| `sensor.bm_reasoning` | Human-readable explanation of the current schedule decision |
| `sensor.bm_forecast` | Price forecast summary with temperature context |
| `sensor.bm_price_ranges` | Active price range classification (load, discharge, adaptive, passive) |
| `sensor.bm_current_action` | Real-time action description during monitoring |
| `sensor.bm_charge_schedule` | Next charge period display (e.g. "⚡ 02:00–04:00") |
| `sensor.bm_discharge_schedule` | Next discharge period display (e.g. "💰 08:00–10:00") |
| `sensor.bm_schedule` | Full schedule as markdown table (charge + discharge periods) |
| `sensor.bm_mode` | Active operating mode (Normal, Passive Solar) |
| `sensor.bm_last_commanded_power` | Last commanded discharge power for adaptive mode (W) |

All entities use `unique_id` for UI management and carry rich attributes (schedule details, price data, timestamps).

## Troubleshooting

- If no schedule is published, verify the Energy Prices price curve sensor exists.
- Ensure the MQTT broker is running and credentials match the add-on configuration.
- Check add-on logs for missing sensor warnings.

## Development

Use the repository runner for local testing:

- python run_addon.py --addon battery-manager
- python run_addon.py --addon battery-manager --once
- python battery-manager/run_local.py
- RUN_ONCE=1 python battery-manager/run_local.py
