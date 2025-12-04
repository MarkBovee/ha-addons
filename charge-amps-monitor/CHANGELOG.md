# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [1.2.4] - 2025-12-04

### Fixed
- Added `hassio_role: homeassistant` to grant full Home Assistant API access
  - Fixes 403 Forbidden when reading price sensor state
  - Required for price-aware charging automation to read entity states

## [1.2.3] - 2025-12-04

### Fixed
- Critical bug: Fixed variable name collision where `base_url` was used for both Charger API and HA API
  - Charger API was receiving HA API URL (`http://supervisor/core/api`) instead of Charge Amps URL
  - This caused 401 Unauthorized errors from Charger API
  - Now uses distinct variable names: `charger_base_url` and `ha_base_url`

## [1.2.2] - 2025-12-04

### Fixed
- Initialize HA API using same pattern as water-heater-scheduler add-on
- Always test HA API connection at startup (required for price reading even when MQTT is used)
- Added debug logging for HA API token detection

## [1.2.1] - 2025-01-26

### Fixed
- Fixed 403 Forbidden error when reading price sensor state in Supervisor environment
  - Added fallback method to get entity state via /states endpoint when direct access fails
  - Some Home Assistant Supervisor versions restrict direct /states/{entity_id} access
- Updated default price sensor entity to match energy-prices add-on: `sensor.energy_prices_price_import`

## [1.2.0] - 2025-12-04

### Added
- **Price-aware charging automation** - automatically schedules charging during cheapest electricity price periods
  - Integrates with energy-prices add-on price sensor
  - Selects top X unique price levels (configurable, default 16)
  - Merges consecutive time slots into continuous charging periods
  - Pushes smart charging schedule to Charge Amps API
- New configuration options:
  - `automation_enabled`: Enable/disable price-aware charging
  - `price_sensor_entity`: Home Assistant price sensor entity ID
  - `top_x_charge_count`: Number of unique price levels to select (more levels = more charging time)
  - `max_current_per_phase`: Maximum charging current in amps
  - `timezone`: Timezone for schedule calculations

### Changed
- Reduced logging verbosity - price analysis now at debug level
- Only logs and pushes schedule when it changes

## [1.1.4] - 2025-12-02

### Fixed
- Ensure numerical values from API are parsed as floats to prevent string arithmetic errors

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
