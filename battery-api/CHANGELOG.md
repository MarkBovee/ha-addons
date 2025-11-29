# Changelog

All notable changes to the Battery API add-on will be documented in this file.

## [0.2.15] - 2025-11-29

### Changed
- Reduced lock contention for faster MQTT schedule response
  - Lock is now held only during API calls, not during status processing
  - MQTT schedule callbacks no longer wait for entire poll cycle
  - Schedule commands now apply immediately when received

## [0.2.14] - 2025-11-29

### Fixed
- Fixed AttributeError in schedule logging (`enable_charge` → `charge_type`)
  - ChargingPeriod uses `charge_type`, `power_w`, `weekdays` not the old attribute names

## [0.2.13] - 2025-11-29

### Improved
- Enhanced logging for schedule save operations:
  - Log each period being saved (start/end time, charge/discharge, power, weekdays)
  - Log API response status and body on both success and failure
  - Log full response JSON on errCode failures
  - Separate HTTPError handling with response body logging
  - Promoted "Saving schedule" log to INFO level for visibility

## [0.2.12] - 2025-11-29

### Changed
- Removed unnecessary API call after schedule apply
  - Previously fetched schedule back from inverter after applying
  - Now updates local state directly from the schedule we just sent
  - Reduces API calls and improves responsiveness

## [0.2.11] - 2025-11-29

### Fixed
- Battery direction was inverted (showed "Charging" when discharging)
  - SAJ API: direction > 0 = discharging, < 0 = charging
  - Now correctly displays "Discharging" when battery power is positive

## [0.2.10] - 2025-11-29

### Fixed
- Added thread safety for SAJ API operations
  - MQTT callbacks (schedule, mode) and main poll loop now use a shared lock
  - Prevents race conditions when schedule arrives during poll cycle
  - Protects `self.status` dict from concurrent modification

## [0.2.9] - 2025-11-29

### Added
- Rich attributes on Battery SOC sensor (mirrors SAJ integration):
  - Device info: plant_name, plant_uid, inverter_model, inverter_sn
  - Battery info: battery_capacity, battery_current, battery_power, battery_direction
  - Grid info: grid_power, grid_direction (Importing/Exporting/Standby)
  - Solar info: photovoltaics_power, photovoltaics_direction, solar_power
  - Load info: total_load_power, home_load_power, backup_load_power
  - Energy totals: battery_charge/discharge_today_energy, battery_charge/discharge_total_energy
  - I/O: input_output_power, output_direction, user_mode, last_update
- Direction attribute on Battery Power sensor (Charging/Discharging/Idle)
- Direction attribute on Grid Power sensor (Importing/Exporting/Standby)

## [0.2.8] - 2025-11-29

### Added
- `schedule_days` config option: "today" (default) applies schedule only to current weekday, "all" applies to all days Mon-Sun
- MQTT password now masked in config UI (changed to `password` type)

### Changed
- Reduced log verbosity: removed banner lines, consolidated to single-line logs
- Mode changes now log as single line instead of multi-line banner
- Startup log simplified to single line

## [0.2.5] - 2025-11-28

### Fixed
- MQTT subscriptions now automatically re-subscribe on reconnection
  - Fixes issue where schedule updates were lost after MQTT broker disconnect/reconnect
  - Command callbacks are stored and re-subscribed in `_on_connect` handler

## [0.2.4] - 2025-11-28

### Added
- Verbose logging every poll cycle (SOC, power values, mode, API status)
- Prominent log banners for mode changes and schedule updates
- MQTT topic `battery_api/text/schedule/set` for receiving schedules

### Fixed
- Schedule delivery now works via direct MQTT subscription (text entity discovery unreliable in HA)

### Changed
- NetDaemon integration now uses MQTT publish instead of text entity service call

## [0.2.3] - 2025-11-28

### Added
- Debug logging for mode changes and schedule input

## [0.2.0] - 2025-11-28

### Added
- Sync battery mode and schedule from inverter on startup
  - Battery mode select now reflects actual inverter mode
  - Schedule text input populated with current inverter schedule

### Removed
- Redundant `sensor.ba_battery_mode` sensor (mode now shown in select entity)
- Redundant `sensor.ba_current_schedule` sensor (schedule now shown in text entity)

### Changed
- Entity count reduced from 12 to 10

## [0.1.1] - 2025-11-28

### Fixed
- Fixed TypeError in main loop: removed extra `logger` argument from `sleep_with_shutdown_check()` call

## [0.1.0] - 2025-01-23

### Added
- Initial release
- SAJ Electric inverter API integration
  - AES-ECB password encryption
  - MD5+SHA1 request signatures
  - Token caching and refresh
- MQTT Discovery entities
  - Control entities: charge/discharge power, duration, start time, schedule type
  - Button entity to apply schedule
  - Status sensors: SOC, mode, API status, last applied
- Schedule management
  - Charge only, discharge only, both, or clear modes
  - Dynamic register address pattern generation
  - Support for multiple time slots
- Simulation mode for testing without affecting inverter
- Configuration via Home Assistant add-on options
