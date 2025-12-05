# Changelog

All notable changes to the Water Heater Scheduler add-on will be documented in this file.

## [1.2.0] - 2025-12-05

### Changed
- **Major rewrite**: Ported scheduling logic directly from proven NetDaemon WaterHeater.cs implementation
- Simplified time window logic using simple hour-based comparisons instead of complex timezone handling
- Removed complex scheduler.py and price_analyzer.py modules in favor of inline functions
- More reliable heating window detection that matches the original C# behavior

### Fixed
- Fixed issue where heating windows were not being triggered at the scheduled time
- Fixed timezone-related edge cases that caused missed heating slots

## [1.1.6] - 2025-12-03

### Added
- Status sensor now keeps announcing the upcoming heating window once the
	current slot has passed, as soon as the next day's prices are available.

## [1.1.5] - 2025-12-03

### Changed
- Simplified status messages to show current state and next planned heating time (e.g., "Idle, heating at 22:00" or "Heating (58°C)").

## [1.1.4] - 2025-12-03

### Changed
- Updated status icons to seasonal thermometer icons (snowflake-thermometer for winter, water-thermometer for summer) with consistent light blue color.

## [1.1.3] - 2025-12-03

### Changed
- Trimmed schedule status messages so only actionable context (planned window, selected target) appears, removing noisy “no data” fragments.

## [1.1.2] - 2025-12-03

### Changed
- Introduced winter-aware icons/colors for the heating status sensors so the UI reflects the season automatically.

## [1.1.1] - 2025-12-03

- Added entity pickers for water heater, price sensor, and helper switches to prevent typos and make the right sensor selectable

### Fixed
- Corrected the add-on schema definition so Home Assistant recognizes the configuration and the add-on appears in the store

## [1.1.0] - 2025-12-02

### Added
- Rolled schema back to the legacy type definitions (no selectors) to maximize Supervisor compatibility.
- Configurable `dynamic_window_mode` option surfaced in UI/schema

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
