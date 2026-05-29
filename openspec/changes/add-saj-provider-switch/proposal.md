## Why

The current SAJ stack depends on the cloud-backed `battery-api` add-on for status, mode changes, and schedule writes, while the new SAJ H2 Modbus integration already exposes local telemetry and local write controls in Home Assistant. A provider switch is needed now so the existing `battery-manager` flow, dashboards, and MQTT contract can keep working while installs move from cloud API control to local Modbus control and unlock extra local-only features.

## What Changes

- Extend `battery-api` with provider selection so it can run against either the current SAJ cloud API or the Home Assistant SAJ Modbus integration.
- Preserve the current `battery_api` MQTT contract for `battery-manager` and existing dashboards: same schedule topic, same normalized status entities, same control entities.
- Add a Modbus-via-Home-Assistant backend that reads mapped SAJ Modbus entities and writes schedules and modes through Home Assistant services instead of direct SAJ cloud calls.
- Add explicit Modbus mapping and conversion config for status entities, writable entities, and watts-to-percent conversion needed by SAJ Modbus charge and discharge slots, with `8000W` as the initial default inverter reference and config override support.
- Add capability detection for optional Modbus-only controls such as passive mode, export limit, and power or depth limits, and explicitly expose export limit because it is useful for negative-price handling.
- Add a safe rollout path with diagnostics, read-back verification, and side-by-side validation before switching a live install from API to Modbus.

## Capabilities

### New Capabilities
- `saj-provider-switch`: Select between SAJ cloud API and SAJ Modbus backends while keeping one stable `battery_api` control contract.
- `saj-modbus-parity`: Support current `battery-api` behavior on top of the SAJ Modbus integration, including normalized status, mode changes, schedule apply, and schedule clear.
- `saj-modbus-extended-controls`: Surface validated Modbus-only controls such as passive mode and export limiting without claiming unsupported features.

### Modified Capabilities

None.

## Impact

- `battery-api/app/main.py`, `battery-api/app/models.py`, `battery-api/config.yaml`, and `battery-api/README.md`
- New backend and mapping modules inside `battery-api/app/`
- Shared Home Assistant service-call usage via `shared/ha_api.py`
- Optional documentation updates in `battery-manager/README.md` and `battery-manager/config.yaml` for rollout guidance
- Real Home Assistant validation against the existing SAJ Modbus device with its current entity set fetched through the configured HA API
