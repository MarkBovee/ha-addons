# Battery Optimizer Add-on

## Purpose

Deliver the current AI-based battery scheduling flow (formerly `Apps/Energy/Battery.cs`) as a Python add-on that talks to SAJ via `BatteryApi`, regenerates schedules hourly, and maintains EMS safeguards without supporting legacy trading/winter/manual strategies.

## Key Behaviors

- Authenticate against SAJ and GitHub Models at startup and refresh tokens automatically.
- Generate a full-day charging/discharging schedule using the AI strategy and re-evaluate every hour or when price/SOC deltas cross thresholds.
- Monitor EMS state, toggle EMS off/on around configured discharge protection windows, and log warnings when battery user mode drifts away from TOU while a schedule is active.
- Persist the latest applied schedule so the add-on survives restarts and validates that Home Assistant + inverter remain synchronized.
- Surface human-readable status updates to the dashboard (`input_text.battery_management_status`) and AI reasoning to `input_text.battery_management_reasoning`.

## User Settings

| Key | Type | Default | Description |
| --- | --- | --- | --- |
| `saj_api_url` | string | `https://globalapi.saj-electric.com` | SAJ API base URL. |
| `saj_username` / `saj_password` | string | – | Credentials for direct inverter control. |
| `github_models.api_key` | string | – | GitHub Models PAT for AI scheduling. |
| `github_models.model` | select | `gpt-4o` | Model identifier used for scheduling prompt. |
| `simulation_mode` | boolean | `false` | Skip hardware writes but generate schedules for testing. |
| `timing.schedule_regen_minutes` | integer | `60` | Interval for forced schedule regeneration. |
| `timing.status_refresh_minutes` | integer | `15` | Interval for silent dashboard refresh. |
| `timing.adaptive_power_minutes` | integer | `5` | How often to verify active periods and EMS state. |
| `ems.enable_toggle` | boolean | `true` | Whether to toggle EMS for morning/evening protection windows. |
| `ems.morning_window` | object | `{"start":"06:00","end":"10:00"}` | EMS off/on schedule for morning peak. |
| `ems.evening_window` | object | `{"start":"17:00","end":"23:00"}` | EMS off/on schedule for evening peak. |
| `soc.min_charge_percent` | integer | `20` | Do-not-discharge threshold. |
| `soc.max_charge_percent` | integer | `100` | Goal SOC used by AI. |
| `solar.peak_sensor_id` | string | `sensor.solar_peak_time` | Sensor containing peak time. |
| `solar.production_sensor_id` | string | `sensor.solar_current_production` | Sensor with current PV output. |
| `ha_entities.status_text_id` | string | `input_text.battery_management_status` | Dashboard status entity. |
| `ha_entities.reasoning_text_id` | string | `input_text.battery_management_reasoning` | AI reasoning text entity. |

## Home Assistant Entities

| Entity | Direction | Description |
| --- | --- | --- |
| `input_text.battery_management_status` | write | Rolling status updates for dashboards. |
| `input_text.battery_management_reasoning` | write | AI explanation for latest schedule. |
| `switch.ems` (or configured EMS switch) | read/write | Toggle EMS state during protection windows. |
| `sensor.ca_battery_schedule_active` | write | Boolean sensor showing whether a schedule is active (new sensor). |
| `sensor.ca_battery_next_charge` / `sensor.ca_battery_next_discharge` | write | Timestamp sensors for upcoming periods. |
| `input_text.battery_management_mode` | read | Monitor current inverter mode to detect mismatches. |
| SAJ battery schedule | write | Applied via API; track success/failure per request. |

## Diagnostics & Logging

- Status text includes both short and verbose entries (with a separate debug log file if needed).
- Structured logs for AI requests/responses, EMS toggles, and mismatched schedules.
- Expose service endpoints: `battery_optimizer.force_regeneration` and `battery_optimizer.clear_state`.

## Future Extensions

- Alternative forecast providers beyond GitHub Models (OpenAI, local heuristics).
- Per-period power overrides or SOC targets for custom strategies.

## Related Documentation

- [Add-on Suite Plan](addon-suite-plan.md)
- [Price Helper Service](price-helper-service-addon.md) – Dependency for electricity pricing
