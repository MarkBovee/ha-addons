# Battery Manager

Price-driven battery scheduling add-on for Home Assistant.

It reads price curves, SOC, grid/solar/load telemetry, and optional EV charger state, then publishes schedules to `Battery API` through MQTT.

## What It Does

- Builds rolling charge and discharge plan from import/export prices
- Regenerates schedule on interval and when live adaptive state drifts from published plan
- Adjusts live discharge behavior during adaptive periods instead of waiting for next hourly plan
- Applies SOC protection, conservative SOC reduction, sell-buffer logic, solar-aware charging, and EV hold rules
- Publishes human-readable status and schedule sensors via MQTT Discovery

## Dependencies

- Home Assistant Supervisor
- MQTT broker, usually `core-mosquitto`
- `Energy Prices` add-on
- `Battery API` add-on

Optional:

- `Charge Amps - EV Charger Monitor` for EV-aware discharge pauses

## Install

1. Add this repository to Home Assistant.
2. Install `Energy Prices` and `Battery API` first.
3. Install `Battery Manager`.
4. Configure entities and thresholds.
5. Start add-on.

## Runtime Model

`Battery Manager` does not talk to inverter directly.

- Reads price curves from `Energy Prices`
- Reads normalized live telemetry from `Battery API`
- Reads provider limits from `sensor.battery_api_api_status`
- Publishes schedule JSON to `battery_api/text/schedule/set`

Because of that, provider switch in `Battery API` should not require dashboard or manager rewiring.

## Core Behavior

### Schedule Generation

- Cheapest periods become charge candidates
- Most expensive periods become discharge candidates
- Mid-range profitable periods can become adaptive discharge windows
- Low-value periods stay passive unless heuristics promote them
- Future sell windows are pruned when current SOC plus planned charging cannot support them

### Live Adaptive Control

- Current interval is checked between full schedule refreshes
- If live interval should stay adaptive but published schedule no longer contains matching adaptive window, add-on regenerates schedule instead of going idle
- Conservative SOC does not hard-stop all live discharge: active adaptive period can downgrade from full discharge to adaptive discharge while respecting reserve floors
- A `0W` adaptive fallback slot is treated as a waiting placeholder, so sell-buffer protection no longer clears later profitable discharge windows before they start

### Solar-Aware Charging

When enabled, planned grid charging for today is reduced by remaining solar forecast so battery still targets `soc.max_soc` without overbuying from grid.

### EV-Aware Protection

When EV charging is active above threshold, discharge can be paused to avoid bad battery economics.

## Configuration

Defaults live in `battery-manager/config.yaml`.

### Important Options

| Option | Meaning |
| --- | --- |
| `enabled` | Master enable |
| `dry_run` | Build and log schedules without publishing |
| `entities.price_curve_entity` | Import price curve sensor |
| `entities.export_price_curve_entity` | Export price curve sensor |
| `entities.remaining_solar_energy_entity` | Remaining solar forecast for today |
| `entities.soc_entity` | SOC sensor, normally `sensor.battery_api_battery_soc` |
| `entities.battery_api_status_entity` | Capability/provider status sensor |
| `entities.grid_power_entity` | Grid power sensor |
| `entities.solar_power_entity` | Solar production sensor |
| `entities.house_load_entity` | House load sensor |
| `entities.battery_power_entity` | Battery power sensor |
| `entities.battery_mode_entity` | Battery mode entity |
| `entities.temperature_entity` | Outdoor temperature sensor |
| `timing.update_interval` | Full schedule refresh interval |
| `timing.monitor_interval` | Live monitor cadence |
| `timing.adaptive_power_grace_seconds` | Minimum gap between adaptive power changes |
| `timing.schedule_regen_cooldown_seconds` | Cooldown for rolling regen |
| `timing.max_soc_sensor_age_seconds` | SOC staleness limit |
| `timing.max_ev_sensor_age_seconds` | EV sensor staleness limit |
| `power.max_charge_power` | Charge ceiling |
| `power.max_discharge_power` | Discharge ceiling |
| `power.min_discharge_power` | Adaptive baseline |
| `power.min_scaled_power` | Minimum scaled schedule power |
| `soc.min_soc` | Hard reserve floor |
| `soc.conservative_soc` | Softer reserve threshold |
| `soc.max_soc` | Max target SOC |
| `soc.battery_capacity_kwh` | Usable capacity for energy math |
| `soc.sell_buffer_*` | Dynamic reserve before planned sell windows |
| `solar_aware_charging.*` | Remaining-solar-aware charge reduction |
| `passive_solar.*` | Excess-solar passive gap logic |
| `heuristics.*` | Price and ranking heuristics |
| `heuristics.charge_spread_enabled` | Spread charging over almost-equal cheap hours instead of always charging flat-out |
| `heuristics.charge_spread_max_price_delta` | Extra cheap-hour tolerance band in EUR/kWh for spread charging |
| `temperature_based_discharge.*` | Temperature-to-discharge-hour mapping |
| `ev_charger.*` | EV integration |
| `negative_price_charging.enabled` | Allow charging logic for negative prices |

### Provider Capabilities

`Battery Manager` no longer assumes fixed `3/6` schedule slots.

It reads `sensor.battery_api_api_status` attributes:

- `capabilities.max_charge_periods`
- `capabilities.max_discharge_periods`

That lets one strategy work with both SAJ cloud API and Modbus backend.

## MQTT and Published Entities

Published entities use `sensor.battery_manager_*` IDs.

| Entity | Purpose |
| --- | --- |
| `sensor.battery_manager_status` | Operational state |
| `sensor.battery_manager_reasoning` | Human-readable rationale |
| `sensor.battery_manager_forecast` | Price and weather summary |
| `sensor.battery_manager_price_ranges` | Current price range classification |
| `sensor.battery_manager_current_action` | Live action summary |
| `sensor.battery_manager_charge_schedule` | Next charge window |
| `sensor.battery_manager_discharge_schedule` | Next discharge window |
| `sensor.battery_manager_schedule` | Main schedule markdown |
| `sensor.battery_manager_schedule_part_2` | Overflow schedule markdown |
| `sensor.battery_manager_mode` | Current runtime mode |
| `sensor.battery_manager_effective_discharge_power` | Effective live discharge power |

Schedule output to `Battery API` uses the existing topic:

```text
battery_api/text/schedule/set
```

## Troubleshooting

### No Schedule Published

1. Verify import/export price sensors exist.
2. Verify MQTT broker is running.
3. Verify `Battery API` is online.
4. Check add-on logs for missing entity warnings.

### Fewer Charge or Discharge Windows Than Expected

1. Check `sensor.battery_api_api_status` capability limits.
2. Check logs for skipped discharge windows due to SOC feasibility.
3. Check temperature-based discharge hour cap.

### Adaptive Discharge Stops Unexpectedly

1. Check SOC against `soc.min_soc` and `soc.conservative_soc`.
2. Check EV charging state and staleness limit.
3. Check current price band still qualifies for adaptive behavior.

### EV Hold Sticks Too Long

Lower `timing.max_ev_sensor_age_seconds` or fix stale EV sensor updates.

### Discharge Windows Disappear

Current versions intentionally prune future sell windows that cannot be supported by current SOC plus already-planned charging.

## Local Development

```bash
python run_addon.py --addon battery-manager
python run_addon.py --addon battery-manager --once
python battery-manager/run_local.py
RUN_ONCE=1 python battery-manager/run_local.py
```

## Related Docs

- [../battery-api/README.md](../battery-api/README.md)
- [../energy-prices/README.md](../energy-prices/README.md)
