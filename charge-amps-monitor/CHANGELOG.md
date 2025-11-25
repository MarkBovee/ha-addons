# Changelog

All notable changes to this project will be documented in this file.

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

### Features
- Monitor charging status (on/off)
- Track total consumption (kWh)
- Monitor current power (W)
- Track voltage and current readings
- Charger online status monitoring
- OCPP status tracking
- Error code reporting
