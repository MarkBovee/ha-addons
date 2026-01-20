# Battery Manager

Optimize battery charging and discharging using dynamic electricity prices, solar surplus, grid export detection, and EV charging awareness.

## Overview

Battery Manager generates daily charge/discharge schedules based on price curves from the Energy Prices add-on. It adjusts discharge behavior in real time for SOC protection, grid export prevention, solar surplus, and EV charging.

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
- **power.min_discharge_power**: minimum discharge power (W)
- **soc.min_soc**: hard minimum SOC (%)
- **soc.conservative_soc**: conservative SOC threshold (%)
- **soc.target_eod_soc**: end-of-day target SOC (%)
- **heuristics.top_x_charge_hours**: cheapest periods to charge
- **heuristics.top_x_discharge_hours**: most expensive periods to discharge
- **heuristics.excess_solar_threshold**: surplus solar threshold (W)
- **temperature_based_discharge.enabled**: enable temperature mapping
- **temperature_based_discharge.thresholds**: temperature → discharge hours mapping
- **ev_charger.enabled**: enable EV charger integration
- **ev_charger.charging_threshold**: EV charging threshold (W)
- **ev_charger.entity_id**: EV charger power sensor

## MQTT Entities

The add-on publishes status entities via MQTT Discovery:

- sensor.battery_manager_status
- sensor.battery_manager_reasoning
- sensor.battery_manager_forecast
- sensor.battery_manager_price_ranges
- sensor.battery_manager_current_action

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
