# Battery API Add-on

Control SAJ Electric inverter battery charge/discharge schedules from Home Assistant.

## Features

- **Entity-based control**: Use Home Assistant number, select, and button entities to configure schedules
- **MQTT Discovery**: Entities are automatically created with proper unique_id support
- **Schedule types**: Charge only, Discharge only, Both, or Clear
- **Simulation mode**: Test without affecting actual inverter

## Requirements

- SAJ Electric inverter with battery storage (H2 series tested)
- Active SAJ eSolar account
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
# SAJ eSolar account credentials
saj_username: "your_email@example.com"
saj_password: "your_password"

# Get these from the SAJ eSolar web portal (Network tab inspection)
device_serial_number: "your_device_serial"
plant_uid: "your_plant_uid"

# Optional settings
poll_interval_seconds: 60
log_level: "info"           # debug, info, warning, error
simulation_mode: false      # Set to true to test without affecting inverter

# MQTT settings (auto-detected if using HA Mosquitto add-on)
mqtt_host: "core-mosquitto"
mqtt_port: 1883
mqtt_username: ""
mqtt_password: ""
```

### Finding Your Device Serial and Plant UID

1. Log into [SAJ eSolar](https://fop.saj-electric.com/)
2. Open browser Developer Tools (F12)
3. Go to Network tab
4. Navigate to your plant/device in eSolar
5. Look for API calls to `eop.saj-electric.com`
6. Find `deviceSnArr` (device serial) and `plantuid` in request payloads

## Entities Created

### Control Entities (inputs)

| Entity | Type | Description |
|--------|------|-------------|
| `number.battery_api_charge_power` | Number | Charge power in watts (0-10000W) |
| `number.battery_api_charge_duration` | Number | Charge duration in minutes |
| `text.battery_api_charge_start_time` | Text | Charge start time (HH:MM format) |
| `number.battery_api_discharge_power` | Number | Discharge power in watts (0-10000W) |
| `number.battery_api_discharge_duration` | Number | Discharge duration in minutes |
| `text.battery_api_discharge_start_time` | Text | Discharge start time (HH:MM format) |
| `select.battery_api_schedule_type` | Select | Schedule type (Charge Only, Discharge Only, Both, Clear) |
| `button.battery_api_apply_schedule` | Button | Apply the configured schedule |

### Status Entities (read-only)

| Entity | Type | Description |
|--------|------|-------------|
| `sensor.battery_api_battery_soc` | Sensor | Current battery state of charge (%) |
| `sensor.battery_api_battery_mode` | Sensor | Current battery operation mode |
| `sensor.battery_api_api_status` | Sensor | API connection status |
| `sensor.battery_api_last_applied` | Sensor | Timestamp of last schedule application |

## Usage Example

### Dashboard Card

```yaml
type: entities
title: Battery Schedule Control
entities:
  - entity: select.battery_api_schedule_type
  - entity: number.battery_api_charge_power
  - entity: number.battery_api_charge_duration
  - entity: text.battery_api_charge_start_time
  - entity: number.battery_api_discharge_power
  - entity: number.battery_api_discharge_duration
  - entity: text.battery_api_discharge_start_time
  - entity: button.battery_api_apply_schedule
  - type: divider
  - entity: sensor.battery_api_battery_soc
  - entity: sensor.battery_api_battery_mode
  - entity: sensor.battery_api_api_status
```

### Automation Example

```yaml
automation:
  - alias: "Schedule battery charge for cheap hours"
    trigger:
      - platform: time
        at: "22:00:00"
    action:
      - service: number.set_value
        target:
          entity_id: number.battery_api_charge_power
        data:
          value: 6000
      - service: number.set_value
        target:
          entity_id: number.battery_api_charge_duration
        data:
          value: 180
      - service: text.set_value
        target:
          entity_id: text.battery_api_charge_start_time
        data:
          value: "02:00"
      - service: select.select_option
        target:
          entity_id: select.battery_api_schedule_type
        data:
          option: "Charge Only"
      - service: button.press
        target:
          entity_id: button.battery_api_apply_schedule
```

## Troubleshooting

### Entities Not Appearing

1. Check that MQTT broker is running (Mosquitto add-on)
2. Verify MQTT credentials in add-on configuration
3. Check add-on logs for connection errors

### Authentication Failures

1. Verify SAJ eSolar credentials are correct
2. Check that device serial and plant UID are correct
3. Enable debug logging to see detailed API responses

### Schedule Not Applied

1. Ensure simulation mode is disabled
2. Check API status sensor for errors
3. Review add-on logs for SAJ API errors

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
```

## Changelog

See [CHANGELOG.md](CHANGELOG.md)

## License

This add-on is released under the MIT License.
