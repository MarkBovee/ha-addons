# Battery API

Home Assistant add-on that exposes a stable battery control contract for SAJ inverters.

It keeps one MQTT topic and one set of normalized `battery_api_*` entities while the backend can run against either:

- SAJ cloud API (`provider: api`)
- Home Assistant SAJ H2 Modbus entities (`provider: modbus_ha`)

`Battery Manager`, dashboards, and ad-hoc automations keep talking to the same contract regardless of provider.

## What It Does

- Publishes normalized battery, PV, grid, load, status, and control entities via MQTT Discovery
- Accepts schedule JSON on `battery_api/text/schedule/set`
- Applies schedules through SAJ cloud API or local Modbus-backed Home Assistant entities
- Exposes provider capabilities through `sensor.battery_api_api_status`
- Supports provider-specific controls like export limit and experimental passive mode when available
- Keeps Modbus polling fast enough for live dashboards and downstream automation

## Current Behavior

- External schedule contract: up to `7` charge periods and `7` discharge periods
- Provider-specific limits are enforced by backend, not by external payload shape
- `provider=api` currently exposes `3` charge and `6` discharge slots
- `provider=modbus_ha` exposes `7` charge and `7` discharge slots
- Default Modbus watts-to-percent reference: `8000W`
- Default poll interval: `10s`
- Empty schedule payload is valid and used for explicit clear: `{"charge":[],"discharge":[]}`
- Safe provider cutover flow: clear schedule, confirm `Self-consumption`, then switch provider

## Requirements

- Home Assistant Supervisor
- MQTT broker reachable by add-on, usually `core-mosquitto`
- SAJ inverter with battery
- For `provider=api`: SAJ eSolar credentials plus device serial and plant UID
- For `provider=modbus_ha`: working SAJ H2 Modbus integration in Home Assistant

## Installation

1. Add `https://github.com/MarkBovee/ha-addons` to Home Assistant Add-on Store.
2. Install `Battery API`.
3. Configure provider and credentials or Modbus-backed setup.
4. Start add-on.

## Configuration

Configure through Home Assistant add-on UI.

```yaml
provider: "api"
poll_interval_seconds: 10
log_level: "info"
simulation_mode: false
modbus_inverter_power_w: 8000
schedule_days: "today"

saj_username: "your_email@example.com"
saj_password: "your_password"
device_serial_number: "your_device_serial"
plant_uid: "your_plant_uid"

mqtt_host: "core-mosquitto"
mqtt_port: 1883
mqtt_user: ""
mqtt_password: ""
```

### Options

| Option | Meaning |
| --- | --- |
| `provider` | `api` or `modbus_ha` |
| `poll_interval_seconds` | Poll cadence, `10-300` seconds |
| `log_level` | `debug`, `info`, `warning`, `error` |
| `simulation_mode` | Skip hardware writes |
| `modbus_inverter_power_w` | Modbus watts reference used to translate schedule power into slot percentages |
| `schedule_days` | `today` applies only current weekday, `all` writes all weekdays |
| `saj_username`, `saj_password`, `device_serial_number`, `plant_uid` | Required for `provider=api` |
| `mqtt_host`, `mqtt_port`, `mqtt_user`, `mqtt_password` | MQTT connection settings |

### SAJ Cloud Values

Find `device_serial_number` and `plant_uid` from SAJ eSolar web traffic.

1. Log in to `https://fop.saj-electric.com/`
2. Open browser dev tools
3. Inspect requests to `eop.saj-electric.com`
4. Copy `deviceSnArr` and `plantuid`

### Modbus Notes

- Add-on UI does not expose free-form `modbus_entities` overrides anymore because Supervisor schema types are limited.
- Runtime still supports advanced `modbus_entities` injection for local/dev use if config is supplied outside normal add-on UI.
- Auto-discovery uses Home Assistant `saj_*` entities and works when mapping is unambiguous.
- Upstream `saj-h2-modbus` should have `fast_enabled=true` for better live telemetry.
- `ultra_fast_enabled` is not relied on for schedule verification.
- `PV off` is intentionally unsupported.
- Experimental passive controls are capability-gated and separate from normal TOU schedule writes.

## MQTT Contract

Schedule commands go to:

```text
battery_api/text/schedule/set
```

Payload shape:

```json
{
  "charge": [
    {"start": "02:00", "duration": 180, "power": 6000}
  ],
  "discharge": [
    {"start": "17:00", "duration": 120, "power": 2500}
  ]
}
```

Rules:

- `start`: `HH:MM`
- `duration`: minutes
- `power`: watts
- No overlapping periods
- End time is clipped to same day; periods never cross midnight
- Clear schedule with empty arrays

Example Home Assistant service call:

```yaml
service: mqtt.publish
data:
  topic: battery_api/text/schedule/set
  payload: >
    {
      "charge": [{"start": "02:00", "duration": 180, "power": 6000}],
      "discharge": [{"start": "17:00", "duration": 120, "power": 2500}]
    }
```

## Entities

### Controls

| Entity | Type | Notes |
| --- | --- | --- |
| `select.battery_api_battery_mode` | Select | Base mode control |
| `text.battery_api_schedule` | Text | JSON schedule input mirror |
| `number.battery_api_export_limit` | Number | Only when backend supports export limit |
| `select.battery_api_passive_mode` | Select | Experimental; only when backend supports passive mode |

### Sensors

| Entity | Type | Notes |
| --- | --- | --- |
| `sensor.battery_api_battery_soc` | Sensor | SOC plus rich power-flow attributes |
| `sensor.battery_api_battery_power` | Sensor | Positive = charging, negative = discharging in normalized contract |
| `sensor.battery_api_pv_power` | Sensor | PV production |
| `sensor.battery_api_grid_power` | Sensor | Positive = import, negative = export |
| `sensor.battery_api_load_power` | Sensor | House load |
| `sensor.battery_api_schedule_status` | Sensor | Validation/apply status |
| `sensor.battery_api_api_status` | Sensor | Connection/provider status plus capability attributes |
| `sensor.battery_api_last_applied` | Sensor | Last successful apply timestamp |

Example `sensor.battery_api_api_status` attributes:

```json
{
  "provider": "modbus_ha",
  "capabilities": {
    "max_charge_periods": 7,
    "max_discharge_periods": 7,
    "export_limit": true,
    "passive_mode": true,
    "experimental_controls": ["passive_mode", "passive_grid_charge_power"],
    "unsupported_controls": ["pv_off"]
  }
}
```

## Battery Manager Integration

`Battery Manager` is expected downstream consumer.

- Reads normalized `battery_api_*` entities
- Publishes schedules to `battery_api/text/schedule/set`
- Reads slot limits from `sensor.battery_api_api_status`
- Does not need provider-specific rewiring during API/Modbus switch

## Troubleshooting

### Add-on Missing From Store

Old builds used unsupported Supervisor schema for `modbus_entities`. Current releases removed that invalid UI schema.

### No Entities In Home Assistant

1. Verify MQTT broker is running.
2. Verify MQTT settings in add-on config.
3. Restart add-on after broker is ready.
4. Check add-on logs for discovery publish errors.

### API Provider Fails

1. Verify SAJ credentials.
2. Verify `device_serial_number` and `plant_uid`.
3. Enable `debug` logging for request diagnostics.

### Modbus Provider Fails

1. Verify SAJ H2 Modbus integration is loaded.
2. Verify required `saj_*` entities exist.
3. Check `sensor.battery_api_api_status` for mapping errors.
4. Check `modbus_inverter_power_w` if slot power translation looks wrong.
5. Keep upstream Modbus integration on `fast_enabled=true`.

### Schedule Looks Stale After Command

Fixed in `0.3.2+`. MQTT command callbacks no longer block polling. If this still happens, inspect logs for missing `Poll:` lines and Home Assistant API latency.

### Modbus Writes Feel Slow

`0.3.3+` and `0.3.4+` reduced write and verify latency by:

- verifying against `*_input` entities
- reusing one Home Assistant state snapshot per cycle
- writing only changed slot fields
- skipping mode writes when target mode already active
- skipping unchanged MQTT publishes

### Provider Cutover

1. Send `{"charge":[],"discharge":[]}`.
2. Confirm inverter falls back to `Self-consumption`.
3. Change `provider`.
4. Restart add-on.
5. Verify `sensor.battery_api_api_status` shows expected provider and capabilities.

## Local Development

```bash
python run_addon.py --addon battery-api --once
```

Typical local `.env` values:

```text
SAJ_USERNAME=
SAJ_PASSWORD=
SAJ_DEVICE_SERIAL=
SAJ_PLANT_UID=
HA_API_URL=http://homeassistant.local:8123
HA_API_TOKEN=
MQTT_HOST=
MQTT_USERNAME=
MQTT_PASSWORD=
SIMULATION_MODE=true
```

Useful files:

- `battery-api/CHANGELOG.md`
- `scripts/verify_api_modbus_schedule_parity.py`
- `battery-api/tests/test_schedule_validation.py`

## Changelog

See [CHANGELOG.md](CHANGELOG.md).
