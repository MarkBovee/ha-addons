# Changelog

All notable changes to the Water Heater Scheduler add-on will be documented in this file.

## [1.1.1] - 2025-12-03

### Improved
- Rebuilt the Supervisor configuration UI using selectors so only the essential fields show by default
- Added entity pickers for water heater, price sensor, and helper switches to prevent typos and make the right sensor selectable

### Fixed
- Corrected the add-on schema definition so Home Assistant recognizes the configuration and the add-on appears in the store

## [1.1.0] - 2025-12-02

### Added
- Dynamic window mode that automatically selects the cheapest day or night window
- Configurable `dynamic_window_mode` option surfaced in UI/schema
- Status sensor now reports the planned window and target in one message and switches its icon (sun vs snowflake) based on day/night programs

## [1.0.0] - 2025-12-02

### Added
- Initial release
- Price-based water heater scheduling
- Temperature presets (eco, comfort, performance, custom)
- Night/Day program logic based on price comparison
- Weekly legionella protection cycle
- Away mode support (optional)
- Bath mode with auto-disable (optional)
- Cycle gap protection to prevent rapid toggling
- Status sensors: `sensor.wh_program`, `sensor.wh_target_temp`, `sensor.wh_status`
- State persistence across container restarts
- MQTT support for entity publishing (when available)
- Local testing via `run_addon.py`
