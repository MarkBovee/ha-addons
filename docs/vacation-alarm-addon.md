# Vacation Alarm Add-on

## Purpose

Automate the night-only alarm arming logic originally in `Apps/Vacation/Alarm.cs`; ensures the alarm is armed when away mode is on between midnight and 07:00, and disarmed otherwise.

## Key Behaviors

- Poll away mode every minute, arm/disarm alarm panel based on time window.
- Use logbook entries to document automatic arming/disarming.
- Provide a bypass switch to pause automation when needed.

## User Settings

| Key | Type | Default | Description |
| --- | --- | --- | --- |
| `alarm_panel_entity_id` | select | – | Alarm control panel to manage. |
| `away_mode_entity_id` | select | `switch.our_home_away_mode` | Source describing if the house is empty. |
| `arm_window` | object | `{"start":"00:00","end":"07:00"}` | Time window during which the alarm is forced to armed-away. |
| `poll_interval_minutes` | integer | `1` | Scheduler cadence. |
| `status_text_entity_id` | string | `input_text.vacation_alarm_status` | Optional status text output. |
| `enable_switch_id` | string | (optional) | HA switch to temporarily disable the automation. |

## Home Assistant Entities

| Entity | Direction | Description |
| --- | --- | --- |
| Configured alarm panel | write | Issue `alarm_arm_away` / `alarm_disarm`. |
| Away-mode switch | read | Determine whether automation should run. |
| `input_text.vacation_alarm_status` | write | Provide human-readable summary. |
| `switch.ca_vacation_alarm_enabled` | write | Toggle to pause automation. |
| Logbook | write | Append entries for arm/disarm events. |

## Diagnostics & Logging

- Track failed service calls to the alarm panel and expose metric counters.
- Provide service `vacation_alarm.force_arm` for manual interventions.

## Future Extensions

- Geofencing integration with presence detection.
- Multiple arm/disarm windows (e.g., midday auto-arm).

## Related Documentation

- [Add-on Suite Plan](addon-suite-plan.md)
