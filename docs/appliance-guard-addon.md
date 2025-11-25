# Appliance Guard Add-on

## Purpose

Recreate the `Appliances.cs` behavior: automatically disable high-load appliances when electricity price level is high or when the home is in away mode, and re-enable them when conditions improve.

## Key Behaviors

- Poll price helper every minute (configurable) and compare against per-appliance thresholds.
- Read the same away-mode switch to aggressively turn everything off when the home is empty.
- Confirm actual load via watt sensors before considering a device idle.
- Write friendly status updates to a global status entity plus per-appliance diagnostics sensors.

## User Settings

| Key | Type | Default | Description |
| --- | --- | --- | --- |
| `away_mode_entity_id` | select | `switch.our_home_away_mode` | Source for away mode. |
| `poll_interval_seconds` | integer | `60` | Scheduler interval for evaluating loads. |
| `price_level_threshold` | select | `High` | Global price tier required to disable devices. |
| `appliances` | list of objects | – | Each entry includes `name`, `switch_entity_id`, `power_sensor_id`, `off_threshold_w`, `re_enable_level`. |
| `status_text_entity_id` | string | `input_text.appliance_guard_status` | Where to log summary text. |
| `enable_automation_switch_id` | string | (optional) | Home Assistant switch to temporarily disable the add-on. |

## Home Assistant Entities

| Entity | Direction | Description |
| --- | --- | --- |
| Configured appliance switches | read/write | Turn devices off/on based on price tier. |
| Configured power sensors | read | Determine if a device is idle (< threshold). |
| `input_text.appliance_guard_status` | write | Summary of recently disabled/enabled appliances. |
| `binary_sensor.ca_appliance_guard_<name>` | write | Per-appliance sensor showing whether it is curtailed. |
| `switch.ca_appliance_guard_enabled` | write | Optional helper switch to pause the automation. |

## Diagnostics & Logging

- Logbook entries whenever an appliance is disabled due to high price.
- Counter metrics (disabled_count, reenable_count) for analytics.

## Future Extensions

- Support priority tiers per appliance to stage curtailment steps.
- Integrate with occupancy sensors for smarter scheduling.

## Related Documentation

- [Add-on Suite Plan](addon-suite-plan.md)
- [Price Helper Service](price-helper-service-addon.md) – Dependency for electricity pricing
