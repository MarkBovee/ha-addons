# Water Heater Scheduler Add-on

## Purpose

Deliver the domestic hot water logic from `WaterHeater.cs`: choose cheapest night/day windows, enforce Saturday legionella cycles, respect bath overrides, and keep the user informed through `input_text.heating_schedule_status`.

## Key Behaviors

- Evaluate price curves every five minutes (configurable) with awareness of today's and tomorrow's prices.
- Choose night vs. day program based on thresholds, adjusting start time ±15 minutes when needed.
- For legionella day, schedule a 3-hour 60–66 °C boost and disable bath mode once water reaches safety temperature.
- Maintain wait cycles to smooth transitions between heating, idle, and bath programs.

## User Settings

| Key | Type | Default | Description |
| --- | --- | --- | --- |
| `water_heater_entity_id` | select | – | Target `water_heater` entity to control. |
| `away_mode_entity_id` | select | `switch.our_home_away_mode` | Away mode source. |
| `bath_mode_entity_id` | select | `input_boolean.bath` | Bath override toggle. |
| `status_text_entity_id` | string | `input_text.heating_schedule_status` | Status output text. |
| `schedule_interval_minutes` | integer | `5` | Frequency of re-evaluation. |
| `night_window` | object | `{"start":"00:00","end":"06:00"}` | Defines the night pricing block. |
| `legionella_day_of_week` | select | `Saturday` | Day to run legionella protection. |
| `legionella_duration_hours` | integer | `3` | Length of legionella boost. |
| `heating_duration_hours` | integer | `1` | Standard program duration. |
| `temperatures.away_legionella` | integer | `60` | Away-mode temperature for legionella cycle. |
| `temperatures.night_program` | integer | `56` | Target temperature for night charge. |
| `temperatures.day_program` | integer | `58` | Target for daytime heating. |
| `temperatures.heating_idle` | integer | `35` | Idle baseline. |
| `temperatures.bath_override` | integer | `50` | Bath target threshold to auto-disable bath mode. |
| `wait_cycles_limit` | integer | `10` | Number of cycles before forcing idle. |
| `next_day_price_check` | boolean | `true` | Whether to compare tomorrow's price before running day program. |

## Home Assistant Entities

| Entity | Direction | Description |
| --- | --- | --- |
| Configured water heater entity | write | Set operation mode and temperature. |
| `input_boolean.bath` | read/write | Disable bath mode when temperature exceeds threshold. |
| `switch.our_home_away_mode` | read | Influences temperature presets. |
| `input_text.heating_schedule_status` | write | Displays next program window or idle message. |
| `sensor.ca_water_heater_next_start` / `sensor.ca_water_heater_next_end` | write | Timestamp sensors for next heating window. |
| `sensor.ca_water_heater_target_temp` | write | Latest target temperature. |
| `sensor.ca_water_heater_program_type` | write | Current program (Idle/Night/Legionella/Away). |

## Diagnostics & Logging

- Debug logs for price selection (night/day comparison, previewed prices 15 minutes before/after).
- Service `water_heater_scheduler.force_run` to recompute immediately.

## Future Extensions

- Support multiple legionella days or manual overrides per week.
- Add energy budget awareness (kWh cap).

## Related Documentation

- [Add-on Suite Plan](addon-suite-plan.md)
- [Price Helper Service](price-helper-service-addon.md) – Dependency for electricity pricing
