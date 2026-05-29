# Battery API Add-on

Control SAJ Electric inverter battery charge/discharge schedules from Home Assistant.

## Features

- **Entity-based monitoring**: Real-time battery SOC, power values, and status via MQTT Discovery
- **Mode control**: Change battery mode (Self-consumption, Time-of-use, AI) via select entity
- **Schedule control**: Accept JSON schedules via MQTT for integration with other automations
- **Provider switch**: Run against the SAJ cloud API or the Home Assistant SAJ H2 Modbus integration
- **Local Modbus support**: Discover live `saj_*` entities through the Home Assistant API and translate the existing schedule contract to Modbus TOU slots
- **Export limit control**: Expose Modbus export limiting when the selected provider supports it
- **MQTT Discovery**: Entities are automatically created with proper unique_id support
- **Simulation mode**: Test without affecting actual inverter

## Requirements

- SAJ Electric inverter with battery storage (H2 series tested)
- Active SAJ eSolar account for provider `api`, or the SAJ H2 Modbus Home Assistant integration for provider `modbus_ha`
- MQTT broker (Mosquitto add-on recommended)

## Installation

1. Add this repository to Home Assistant Add-on Store:
   - Go to Settings → Add-ons → Add-on Store
   - Click the three dots menu (⋮) → Repositories
   - Add: `https://github.com/MarkBovee/ha-addons`

2. Install the "Battery API" add-on

3. Configure the add-on with your SAJ credentials (see Configuration below)

4. Start the add-on

## Configuration

```yaml
# Provider selection
provider: "api"              # api or modbus_ha

# SAJ eSolar account credentials (required for provider=api)
saj_username: "your_email@example.com"
saj_password: "your_password"

# Get these from the SAJ eSolar web portal (Network tab inspection)
device_serial_number: "your_device_serial"
plant_uid: "your_plant_uid"

# Optional settings
poll_interval_seconds: 60
log_level: "info"           # debug, info, warning, error
simulation_mode: false      # Set to true to test without affecting inverter
modbus_inverter_power_w: 8000  # Default Modbus watts->percent reference

# Optional Modbus entity overrides for provider=modbus_ha
modbus_entities: {}

# MQTT settings (auto-detected if using HA Mosquitto add-on)
mqtt_host: "core-mosquitto"
mqtt_port: 1883
mqtt_user: ""
mqtt_password: ""
```

### Finding Your Device Serial and Plant UID

1. Log into [SAJ eSolar](https://fop.saj-electric.com/)
2. Open browser Developer Tools (F12)
3. Go to Network tab
4. Navigate to your plant/device in eSolar
5. Look for API calls to `eop.saj-electric.com`
6. Find `deviceSnArr` (device serial) and `plantuid` in request payloads

### Modbus Provider Notes

- The add-on keeps the same MQTT topic and normalized `battery_api_*` entities for both providers.
- The schedule contract now accepts up to 7 charge periods and 7 discharge periods; provider-specific limits are exposed via `sensor.battery_api_api_status` attributes instead of being hardcoded into the payload contract.
- For provider `modbus_ha`, the add-on queries Home Assistant directly and prefills known live `saj_*` entities when discovery is unambiguous.
- The current install uses `8000W` as the default inverter reference for converting requested watts to Modbus slot percentages.
- Export limit is exposed when `number.saj_export_limit_input` is available.
- Passive mode mappings can be detected, but they remain experimental and are not advertised as supported in phase 1.
- `PV off` is intentionally unsupported until a validated control path exists.
- Upstream `saj-h2-modbus` should have `fast_enabled=true` for snappier live power telemetry. Schedule slot read-back still depends on explicit `homeassistant.update_entity` refreshes; `ultra_fast_enabled` is not used as schedule verification.
- Safe cutover stays explicit: clear schedule with `{"charge":[],"discharge":[]}`, confirm fallback `Self-consumption`, then flip provider.

## Entities Created

### Control Entities

| Entity | Type | Description |
|--------|------|-------------|
| `select.battery_api_battery_mode` | Select | Battery mode (Self-consumption, Time-of-use, AI) |

### Status Entities (read-only)

| Entity | Type | Description |
|--------|------|-------------|
| `sensor.battery_api_battery_soc` | Sensor | Current battery state of charge (%) |
| `sensor.battery_api_battery_power` | Sensor | Battery power in watts (+ charging, - discharging) |
| `sensor.battery_api_pv_power` | Sensor | Solar PV power in watts |
| `sensor.battery_api_grid_power` | Sensor | Grid power in watts (+ import, - export) |
| `sensor.battery_api_load_power` | Sensor | House load power in watts |
| `sensor.battery_api_schedule_status` | Sensor | Schedule validation/sync status |
| `sensor.battery_api_api_status` | Sensor | Provider connection status plus capability attributes |
| `sensor.battery_api_last_applied` | Sensor | Timestamp of last schedule application |

When provider `modbus_ha` exposes export limiting, the add-on also publishes `number.battery_api_export_limit`.

### Battery Modes

- **Self-consumption**: Battery charges from excess solar, discharges to reduce grid import
- **Time-of-use**: Battery follows configured charge/discharge schedule
- **AI**: Inverter's AI-driven optimization mode

## Schedule Control via MQTT

The add-on listens for schedule commands on the MQTT topic: `battery_api/text/schedule/set`

### Schedule JSON Format

```json
{
  "charge": [
    {"start": "02:00", "duration": 180, "power": 6000}
  ],
  "discharge": [
    {"start": "17:00", "duration": 120, "power": 3000}
  ]
}
```

- `start`: Start time in HH:MM format
- `duration`: Duration in minutes
- `power`: Power in watts

### Sending a Schedule via Home Assistant

```yaml
service: mqtt.publish
data:
  topic: "battery_api/text/schedule/set"
  payload: >
    {
      "charge": [{"start": "02:00", "duration": 180, "power": 6000}],
      "discharge": [{"start": "17:00", "duration": 120, "power": 2500}]
    }
```

### Provider Limits

- Payload contract: up to 7 charge periods and 7 discharge periods
- Active provider limits are published in `sensor.battery_api_api_status` attributes under `capabilities.max_charge_periods` and `capabilities.max_discharge_periods`
- Provider `api` currently reports `3` charge and `6` discharge slots
- Provider `modbus_ha` currently reports `7` charge and `7` discharge slots
- Periods cannot overlap
- Period end times must not cross midnight; durations are normalized so each period ends by `23:59`

Example `sensor.battery_api_api_status` attributes:

```json
{
  "provider": "modbus_ha",
  "capabilities": {
    "max_charge_periods": 7,
    "max_discharge_periods": 7,
    "export_limit": true,
    "passive_mode": false,
    "unsupported_controls": ["pv_off"]
  }
}
```

## Integration with NetDaemon

This add-on is designed to work with NetDaemon for automated battery management. NetDaemon calculates optimal charge/discharge schedules based on electricity prices and solar forecasts, then publishes them to this add-on via MQTT.

The add-on then:
1. Validates the schedule
2. Applies it to the SAJ inverter via the selected provider backend
3. Updates the `sensor.battery_api_schedule_status` with the result

## Dashboard Card Example

```yaml
type: entities
title: Battery Status
entities:
  - entity: sensor.battery_api_battery_soc
  - entity: sensor.battery_api_battery_power
  - entity: sensor.battery_api_pv_power
  - entity: sensor.battery_api_grid_power
  - entity: sensor.battery_api_load_power
  - type: divider
  - entity: select.battery_api_battery_mode
  - entity: sensor.battery_api_schedule_status
  - entity: sensor.battery_api_api_status
```

## Troubleshooting

### Entities Not Appearing

1. Check that MQTT broker is running (Mosquitto add-on)
2. Verify MQTT credentials in add-on configuration
3. Check add-on logs for connection errors
4. Restart the add-on after MQTT broker is running

### Authentication Failures

1. Verify SAJ eSolar credentials are correct
2. Check that device serial and plant UID are correct
3. Enable debug logging to see detailed API responses

### Schedule Not Applied

1. Ensure simulation mode is disabled
2. Check `sensor.battery_api_schedule_status` for validation errors
3. Check `sensor.battery_api_api_status` shows "Connected"
4. Check `sensor.battery_api_api_status` attributes for provider limits and capability flags
5. Review add-on logs for provider-specific errors and read-back mismatches

### Modbus Mapping Problems

1. Verify the SAJ H2 Modbus integration is loaded and the `saj_*` entities exist in Home Assistant
2. Check `sensor.battery_api_api_status` for missing mapping diagnostics
3. Override `modbus_entities` only if auto-discovery picked the wrong entity IDs
4. Confirm `modbus_inverter_power_w` matches the real inverter size if slot power looks wrong
5. Enable upstream SAJ Modbus `fast_enabled=true` for better live power telemetry
6. If mode or export-limit writes fail verification, check the live HA entity state and integration latency; mode propagation can lag enough that verification needs a longer wait than slot refreshes

### Provider Switch Rollout

1. Start from a known-good baseline and read `sensor.battery_api_api_status` attributes.
2. Clear current schedule with `{"charge":[],"discharge":[]}`.
3. Confirm battery mode falls back to `Self-consumption`.
4. Change `provider` to `modbus_ha`.
5. Restart add-on and verify `sensor.battery_api_api_status` now shows `provider=modbus_ha` with expected slot caps.
6. Keep `battery-manager` and dashboards unchanged; they continue using the same topic and normalized entities.
7. A validated live cutover now exists for clear -> self-consumption -> restore back to time-of-use schedule.

### Clearing a Schedule

To clear all charge/discharge periods, send an empty schedule:

```yaml
service: mqtt.publish
data:
  topic: "battery_api/text/schedule/set"
  payload: '{"charge": [], "discharge": []}'
```

## Development

### Local Testing

```bash
cd ha-addons
python run_addon.py --addon battery-api --once
```

Requires `.env` file with:
```
SAJ_USERNAME=your_email
SAJ_PASSWORD=your_password
SAJ_DEVICE_SERIAL=your_serial
SAJ_PLANT_UID=your_plant_uid
SIMULATION_MODE=true
HA_API_URL=http://your-ha-ip:8123
HA_API_TOKEN=your-long-lived-token
MQTT_HOST=your-mqtt-broker
MQTT_USERNAME=mqtt-user
MQTT_PASSWORD=mqtt-password
```

### Test Scripts

- `test_schedule.py` - Test sending schedules via MQTT
- `cleanup_mqtt_entities.py` - Remove all MQTT discovery entities (for debugging)

## Changelog

See [CHANGELOG.md](CHANGELOG.md)

## License

This add-on is released under the MIT License.
