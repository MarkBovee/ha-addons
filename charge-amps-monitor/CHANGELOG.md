# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [1.3.5] - 2025-12-26

### Fixed
- Re-run price analysis after 13:00 when tomorrow's prices become available (without needing a restart)
- Adds a once-per-afternoon refresh if tomorrow slots were missing earlier in the day

## [1.3.4] - 2025-12-24

### Fixed
- Fixed `top_x_charge_count`, `price_threshold`, and `operation_mode` config settings not being read from options.json
- Added missing environment variable exports in run.sh
- These settings now properly affect schedule generation

## [1.3.3] - 2025-12-24

### Fixed
- Fixed schedule not updating daily by using stable Monday week anchor instead of daily-changing anchor
- Schedule now persists and updates correctly throughout the week
- Week transition detection forces schedule refresh when crossing into new week

## [1.3.2] - 2025-12-22

### Fixed
- Fixed schedule appearing on wrong day by anchoring week start to "today at midnight" instead of "most recent Sunday"

## [1.3.1] - 2025-12-21

### Fixed
- Prevent `SCHEDULE_INVALID_DATA` ("Periods From value can not exceed 604800") by anchoring the schedule week at Sunday 00:00 and clamping pushed periods to the Charge Amps 7-day window.

## [1.3.0] - 2025-01-XX

### Added
- **HEMS Operation Mode** - support for external schedule control via MQTT
  - New `operation_mode` config: `standalone` (default) or `hems`
  - HEMS mode subscribes to `hems/charge-amps/{connector_id}/schedule/set` and `/schedule/clear` topics
  - Publishes status to `hems/charge-amps/{connector_id}/status`
  - Prepares for future integration with battery-optimizer or other HEMS systems
- **Price Threshold Filtering** - limit charging to slots below a max price
  - New `price_threshold` config (default: 0.25 EUR/kWh)
  - Slots above threshold are excluded before unique price selection
  - New `binary_sensor.ca_price_threshold_active` shows when threshold filtered any slots
- **New Sensors**:
  - `sensor.ca_schedule_source` - shows `standalone`, `hems`, or `none`
  - `sensor.ca_hems_last_command` - timestamp of last HEMS command (diagnostic)
  - `binary_sensor.ca_price_threshold_active` - indicates if threshold excluded any slots

### Changed
- **Slot Selection Behavior** (breaking): `top_x_charge_count` now selects top X unique price *levels* instead of raw slot count
  - Example: With `top_x_charge_count: 2`, if 4 slots exist at €0.08 and 3 at €0.10, all 7 slots are selected (2 price levels)
  - This provides more charging time when multiple slots share the same low price
  - Users wanting exact slot count can set a low `price_threshold` to limit selection

### Fixed
- Changed price unit in logs from "cents/kWh" to "EUR/kWh" for consistency

## [1.2.6] - 2025-12-04

### Fixed
- Fixed HA API URL in run.sh: was `http://supervisor/core` but should be `http://supervisor/core/api`
  - This was the root cause of all 403 Forbidden errors when reading price sensor

## [1.2.5] - 2025-12-04

### Changed
- Added debug logging to HA API test_connection and fallback methods to diagnose 403 errors

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
- Updated default price sensor entity to match energy-prices add-on: `sensor.energy_prices_electricity_import_price`

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
