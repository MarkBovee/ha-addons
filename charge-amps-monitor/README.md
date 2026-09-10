# Charge Amps Monitor

Charge Amps Monitor is a Home Assistant Supervisor add-on for monitoring Charge Amps EV chargers and integrating their available scheduling capabilities into Home Assistant.

## What It Does

- Monitors Charge Amps charger and connector state.
- Publishes charging state and online status to Home Assistant.
- Publishes charging power, current, voltage, and cumulative energy when supplied by the charger.
- Provides normalized read-only entities introduced in version 2.0.0 and corrected in 2.0.1.
- Generates and manages price-based charging schedules in standalone mode.
- Keeps existing REST entities, MQTT Discovery entities, and legacy schedule compatibility available during migration.
- Runs without HEMS when standalone scheduling is enabled or automation is disabled.

Direct charger start, stop, persistent current control, and connector enable/disable are not exposed. The corresponding Charge Amps provider operations and limits have not been verified, so the add-on does not publish fake writable controls.

## Home Assistant Integration

The add-on exposes charger information and supported schedule functionality through Home Assistant entities. Monitoring entities are read-only. Schedule generation uses the configured price sensor and add-on settings; it does not provide direct charger start/stop or current commands.

The target HEMS architecture is:

```text
HEMS
  |
  v
Home Assistant entities and services
  |
  v
Charge Amps integration
  |
  v
Charge Amps charger
```

Future HEMS integrations use Home Assistant entity state, events, and services. They do not use Charge Amps-specific APIs, Python classes, databases, or MQTT topics.

## Standalone Mode

Standalone mode is the default. When automation is enabled, the add-on reads price data from the configured Home Assistant price sensor, filters slots above the optional price threshold, selects the configured number of cheapest unique price levels, merges adjacent slots, and writes the resulting weekly schedule to Charge Amps.

The configured maximum current is written into generated schedule periods. It is a schedule parameter, not persistent direct charger current control. Schedule writes are read back and failed or unverifiable operations are reported as errors.

HEMS is optional. Monitoring and standalone price-based scheduling do not require a future HEMS service.

## HEMS Compatibility

Existing installations may continue to use the legacy schedule compatibility ingress in `hems` mode. It accepts schedule set and clear messages and reports whether the corresponding schedule operation succeeded.

This compatibility ingress is temporary add-on plumbing, not the target HEMS interface. It must not be used as a general HEMS integration contract. The target contract remains Home Assistant entities and services. Existing compatibility topics are:

- `hems/charge-amps/{connector_id}/schedule/set`
- `hems/charge-amps/{connector_id}/schedule/clear`
- `hems/charge-amps/{connector_id}/status`

## Installation

### Custom Repository

1. Open **Settings > Add-ons > Add-on Store** in Home Assistant.
2. Open the three-dot menu and choose **Repositories**.
3. Add `https://github.com/MarkBovee/ha-addons`.
4. Install **Charge Amps - EV Charger Monitor**.
5. Configure the add-on and start it.

### Local Add-on

Copy `charge-amps-monitor` to `/config/addons/`, then open the add-on store and select **Check for updates**. Install and configure the local add-on.

## Configuration

Configure these options in the Home Assistant add-on UI. Existing option names remain unchanged.

| Option | Description |
| --- | --- |
| `email` | Charge Amps account email address. |
| `password` | Charge Amps account password. |
| `host_name` | Charge Amps account host name. Default: `my.charge.space`. |
| `base_url` | Charge Amps service base URL. Default: `https://my.charge.space`. |
| `update_interval` | Minutes between charger status updates. |
| `operation_mode` | `standalone` for price-based scheduling or `hems` for legacy external schedule compatibility. |
| `automation_enabled` | Enables standalone price-based schedule generation. Monitoring remains available when disabled. |
| `price_sensor_entity` | Home Assistant entity containing import prices in EUR/kWh. |
| `top_x_charge_count` | Number of unique low-price levels selected per day. This is not a raw slot count. |
| `price_threshold` | Optional maximum price in EUR/kWh. Slots above this value are excluded. |
| `max_current_per_phase` | Current value written into generated schedule periods. This does not enable direct current control. |
| `connector_ids` | Comma-separated Charge Amps connector IDs. The current runtime uses the first valid ID. |
| `mqtt_host` | Optional MQTT broker host for Home Assistant Discovery and legacy compatibility. Default: `core-mosquitto`. |
| `mqtt_port` | Optional MQTT broker port. Default: `1883`. |
| `mqtt_user` | Optional MQTT username. |
| `mqtt_password` | Optional MQTT password. |

The schedule timezone is detected from Home Assistant automatically. `CHARGER_TIMEZONE` is only a local-development fallback when Home Assistant does not provide a timezone.

## Entities

### Normalized Entities

These additive entities are the preferred capability-oriented interface for future HEMS use. They are read-only unless a future release verifies and implements a provider operation.

| Entity | Meaning |
| --- | --- |
| `sensor.charge_amps_monitor_state` | Normalized charger status such as `available`, `charging`, `offline`, or `faulted`. |
| `binary_sensor.charge_amps_monitor_online` | Whether the charger currently reports as online. |
| `binary_sensor.charge_amps_monitor_charging` | Whether the connector currently reports charging. |
| `sensor.charge_amps_monitor_power` | Measured charging power in W. |
| `sensor.charge_amps_monitor_energy` | Cumulative charging energy in kWh. |
| `sensor.charge_amps_monitor_current` | Measured charging current in A. |
| `sensor.charge_amps_monitor_voltage` | Measured charging voltage in V. |
| `sensor.charge_amps_monitor_capabilities` | Diagnostic summary of verified, unsupported, and unknown capabilities. The current result is read-only. |
| `sensor.charge_amps_monitor_error` | Last provider or integration error. |

Missing measurements are unavailable rather than fabricated as zero. If a provider refresh fails, normalized live measurements are marked unavailable.

### Legacy REST Entities

The REST fallback keeps existing entity IDs for compatibility. These entities are state snapshots; their historical `input_boolean` and `input_number` domains are not supported charger controls.

- `input_boolean.ca_charger_charging` - Charging state.
- `input_number.ca_charger_total_consumption_kwh` - Cumulative charging energy in kWh.
- `input_number.ca_charger_current_power_w` - Charging power in W.
- `sensor.ca_charger_status` - Charger status.
- `sensor.ca_charger_power_kw` - Charging power in kW.
- `sensor.ca_charger_voltage` - Average charging voltage in V.
- `sensor.ca_charger_current` - Average charging current in A.
- `binary_sensor.ca_charger_online` - Online status.
- `binary_sensor.ca_charger_connector_enabled` - Provider-reported connector enabled state.
- `input_text.ca_charger_name` - Charger name.
- `input_text.ca_charger_serial` - Charger serial number.
- `sensor.ca_charger_connector_mode` - Connector mode diagnostic.
- `sensor.ca_charger_ocpp_status` - Connector protocol status diagnostic.
- `sensor.ca_charger_error_code` - Provider error code when present.
- `sensor.ca_charging_schedule_status` - Schedule state.
- `sensor.ca_next_charge_start` - Next scheduled charging start.
- `sensor.ca_next_charge_end` - Next scheduled charging end.
- `sensor.ca_charging_schedule_error` - Last schedule error.

### MQTT Discovery Entities

When MQTT Discovery is available, existing `charge_amps_*` entities remain published. Their exact entity registry names are based on the existing `charge_amps` prefix. The normalized entities use the `charge_amps_monitor_*` prefix described above.

MQTT is an internal publication and compatibility mechanism. It is not the HEMS integration boundary.

### Supported Controls

Version 2.0.1 exposes no direct charger start, stop, persistent current, or connector enable/disable controls. The add-on can manage verified Charge Amps schedules from standalone automation and the legacy compatibility path. A schedule refresh button, when available through MQTT Discovery, refreshes price analysis; it does not directly start or stop the charger.

## Limitations

Direct start, stop, persistent current control, and connector enable/disable are not currently exposed because the corresponding Charge Amps provider operations have not been verified.

Provider current limits and phase constraints are also not verified. The add-on does not invent limits, silently clamp requests, or publish writable current entities.

The `battery-manager` configuration references `sensor.charge_amps_monitor_charger_current_power`. Charge Amps Monitor preserves this compatibility entity and its `charge_amps_current_power` unique ID while the normalized entities remain additive.

## Troubleshooting

- Check add-on logs under **Settings > Add-ons > Charge Amps - EV Charger Monitor > Log**.
- Verify Charge Amps credentials and network access to `my.charge.space`.
- Verify the configured price sensor exists and exposes usable EUR/kWh data when standalone automation is enabled.
- Check that Home Assistant API access is available to the add-on.
- If normalized measurements are unavailable, inspect the provider refresh error and Charge Amps charger connectivity.

## Local Development

```bash
cd charge-amps-monitor
pip install -r requirements.txt
cp .env.example .env
python run_local.py
```

Run the test suite with:

```bash
pytest -q tests
```

The add-on uses Python 3.12+ and Home Assistant Supervisor APIs. The Charge Amps API and MQTT transport are implementation details below the Home Assistant integration boundary.

## License

This project is licensed under the MIT License. See [LICENSE](../LICENSE).
