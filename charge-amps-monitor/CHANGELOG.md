# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [1.1.3] - 2025-11-26

### Changed
- Refactored to use shared modules (`shared/addon_base.py`, `shared/ha_api.py`, etc.)
- Migrated from global `shutdown_flag` to `threading.Event` pattern for cleaner shutdown handling
- Consolidated Home Assistant API code into reusable `HomeAssistantApi` class

## [1.1.2] - 2025-11-25

### Added
- MQTT credentials now configurable in add-on UI (`mqtt_user`, `mqtt_password`)
- Default MQTT settings exposed: `mqtt_host: core-mosquitto`, `mqtt_port: 1883`

## [1.1.1] - 2025-11-25

### Fixed
- Updated MQTT callbacks for paho-mqtt 2.x API compatibility
- `_on_connect` and `_on_disconnect` now handle ReasonCode objects correctly

## [1.1.0] - 2025-11-25

### Added
- **MQTT Discovery support** for entities with proper `unique_id`
  - Entities can now be renamed, hidden, and managed from HA UI
  - Entities are grouped under "Charge Amps Monitor" device in HA
  - Automatically detects Mosquitto MQTT broker
- Optional MQTT configuration: `mqtt_host`, `mqtt_port`, `mqtt_user`, `mqtt_password`
- Falls back to REST API if MQTT broker is not available

### Changed
- Entity names when using MQTT: `sensor.charge_amps_power_kw`, etc.
- Device info shows manufacturer "Charge Amps" and model "EV Charger"

## [1.0.7] - 2025-11-25

### Changed
- Reduced routine logging noise by limiting entity-by-entity messages to the initial verbose startup pass.

### Added
- Packaged a Charge Amps icon (`icon.png`) so the add-on is recognizable inside Home Assistant.

## [1.0.6] - 2025-11-25

### Fixed
- Enabled Home Assistant API access to prevent 401 errors when updating entities.

### Changed
- Reformatted this changelog to fully follow the Keep a Changelog convention.

## [1.0.5] - 2024-11-24

### Changed
- Modified Home Assistant API URL in run.sh and main.py
- Enhanced logging for API token presence and connection tests

## [1.0.4] - 2024-11-23

### Added
- Initial release of Charge Amps EV Charger Monitor
- Automatic entity creation for charging status, power, and consumption
- Periodic updates with configurable interval
- Secure authentication with Charge Amps API
- Comprehensive monitoring of charger status and metrics
- Support for multiple architectures (aarch64, amd64, armhf, armv7, i386)
- Monitor charging status (on/off)
- Track total consumption (kWh)
- Monitor current power (W)
- Track voltage and current readings
- Charger online status monitoring
- OCPP status tracking
- Error code reporting
