# Changelog

All notable changes to the Water Heater Scheduler add-on will be documented in this file.

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
