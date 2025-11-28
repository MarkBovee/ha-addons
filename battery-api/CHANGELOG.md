# Changelog

All notable changes to the Battery API add-on will be documented in this file.

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
