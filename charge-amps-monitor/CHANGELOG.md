# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

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
