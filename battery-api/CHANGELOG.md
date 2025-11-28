# Changelog

All notable changes to the Battery API add-on will be documented in this file.

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
