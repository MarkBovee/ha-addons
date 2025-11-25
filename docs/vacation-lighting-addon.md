# Vacation Lighting Add-on

## Purpose

Simulate presence when the home is empty by turning on a rotating list of lights when vacation mode is active, following the behavior from `LightsOnVacation.cs`.

## Key Behaviors

- Discover light/switch entities whose ids or friendly names match include keywords while avoiding exclude keywords.
- When vacation mode is on, turn on a randomized subset of lights at sunset, reshuffle hourly, and turn everything off at a configured time (e.g., 00:30).
- Provide status updates via input_text and store the nightly selection for dashboards.

## User Settings

| Key | Type | Default | Description |
| --- | --- | --- | --- |
| `vacation_mode_entity_id` | select | `input_boolean.vacation_mode` | Drives whether automation is active. |
| `lights_per_day` | integer | `3` | Number of lights to activate at sunset. |
| `sunset_offset_minutes` | integer | `0` | Offset relative to actual sunset (negative to start earlier). |
| `lights_off_time` | time | `00:30` | Time of day to force all lights off. |
| `include_keywords` | list | `["light","lamp","led","spot","moodlight","verlichting"]` | Keywords for discovery. |
| `exclude_keywords` | list | `["badkamer","vaatwasser","tv","computer","audio","droger","vriezer","ems","wasmachine","auto_off","auto_update","shuffle","repeat","do_not_disturb"]` | Prevents selecting undesired entities. |
| `random_seed_mode` | select | `daily` | Options: `daily` (seed by day of year) or `true_random`. |
| `status_text_entity_id` | string | `input_text.vacation_lights_management_status` | Dashboard output. |
| `selected_lights_sensor_id` | string | `sensor.ca_vacation_lights_selection` | Stores tonight's lineup. |

## Home Assistant Entities

| Entity | Direction | Description |
| --- | --- | --- |
| Discovered lights/switches | write | Turn on/off for presence simulation. |
| `input_text.vacation_lights_management_status` | write | Friendly updates ("Selected lights: …"). |
| `sensor.ca_vacation_lights_selection` | write | JSON list of tonight's lights with start times. |
| `switch.ca_vacation_lights_enabled` | write | Optional override switch. |

## Diagnostics & Logging

- Log discovery summary and reasons for excluding entities.
- Services: `vacation_lighting.regenerate_selection` and `vacation_lighting.turn_off_all`.

## Future Extensions

- Integrate with media players or blinds for richer simulations.
- Support seasonal profiles (winter vs summer offsets).

## Related Documentation

- [Add-on Suite Plan](addon-suite-plan.md)
