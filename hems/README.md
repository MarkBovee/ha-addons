# HEMS Add-on

Home Energy Management System add-on that applies the Range-Based battery strategy with adaptive control. Uses the `energy-prices` add-on for import prices and the `battery-api` add-on to apply schedules. EMS toggling is intentionally omitted; opportunistic solar is optional.

## Overview
- Rolling 15-minute schedule based on current price range (load/adaptive/discharge)
- 1-minute adaptive discharge adjustments using 1-minute average power sensor
- 15-minute status refresh; daily full reload at 01:00; hourly regeneration
- Optional opportunistic solar when export is detected and sun is up
- Applies schedules to the `battery-api` add-on via MQTT (`battery_api/text/schedule/set`) using HA's `mqtt.publish`
- **Simulation mode** available to observe decisions without writing schedules or sensors

## Requirements
- Home Assistant API access (`homeassistant_api: true`)
- `energy-prices` add-on providing `sensor.energy_prices_electricity_import_price`
- `battery-api` add-on available (`sensor.battery_api_api_status` healthy)
- Sensors:
  - `sensor.battery_api_load_power` (1m average import/export)
  - `sensor.battery_api_battery_power` (+charge / -discharge)
  - `sensor.battery_api_grid_power` (+import / -export)
  - `sensor.battery_api_battery_soc`
  - Optional solar: `sensor.power_production_now`, `sun.sun`, forecast sensors
  - Optional MQTT discovery is not required; schedule is sent via HA service call

## Configuration
Key options (see `config.yaml` for full schema):
- `price_sensor_entity_id`: fixed to `sensor.energy_prices_electricity_import_price`
- `average_power_sensor_entity_id`: `sensor.battery_api_load_power` (positive import, negative export)
- `battery_power_sensor_entity_id`: `sensor.battery_api_battery_power` (+charge / -discharge)
- `battery_grid_power_sensor_entity_id`: `sensor.battery_api_grid_power` (+import / -export)
- `battery_soc_sensor_entity_id`: `sensor.battery_api_battery_soc`
- Power/SOC: `max_inverter_power_w`, `default_charge_power_w`, `default_discharge_power_w`, `min_discharge_power_w`, `min_scaled_power_w`, `conservative_soc_threshold_percent`, `minimum_discharge_soc_percent`
- Price windows: `topx_charge_count`, `topx_discharge_count`
- Timing: `adaptive_monitor_interval_minutes` (default 1), `status_refresh_minutes` (15), `daily_reload_time` (01:00), `hourly_regeneration` (true)
- Adaptive thresholds: `adaptive_disable_threshold_w`, `adaptive_power_increment_w`
- Temperature-based discharge: enable + forecast/fallback sensors
- Solar: `enable_opportunistic_solar` and solar/sun sensors
- `simulation_mode`: when true, all HA writes are suppressed; logs show what would be published

## Outputs
- `sensor.hems_status`: status plus attributes for next charge/discharge and last publish time
- `sensor.hems_adaptive_power_w`: last adaptive discharge target (W)

## Schedule publishing
- Uses HA service call `mqtt.publish` to send schedule JSON to `battery_api/text/schedule/set`
- SAJ limits enforced: max 3 charge and 6 discharge windows; 15-minute granularity
- Charge/discharge power capped by `max_inverter_power_w` and SOC thresholds

## Running
The add-on starts automatically and runs `/app/app.main`. No MQTT credentials are required unless you enable MQTT discovery in code.

## Notes
- EMS toggling is not supported.
- Prices are taken only from the HA sensor; no external fallback.
