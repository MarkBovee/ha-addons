# Changelog

All notable changes to the Energy Prices add-on will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.3.0] - 2025-11-25

### Added
- **MQTT Discovery support** for entities with proper `unique_id`
  - Entities can now be renamed, hidden, and managed from HA UI
  - Entities are grouped under "Energy Prices" device in HA
  - Automatically detects Mosquitto MQTT broker
- Optional MQTT configuration: `mqtt_host`, `mqtt_port`, `mqtt_user`, `mqtt_password`
- Falls back to REST API if MQTT broker is not available

### Changed
- Entity names when using MQTT: `sensor.energy_prices_price_import`, etc.
- Device info shows manufacturer "HA Addons" and model "Nord Pool Price Monitor"

## [1.2.6] - 2025-11-25

### Added
- Support for RUN_ONCE mode (exit after single iteration for testing)
- Works with `python run_addon.py --addon energy-prices --once`

## [1.2.5] - 2025-11-25

### Changed
- Delete old entities on startup to ensure clean state
- Only log entity creation details on first run, subsequent updates show compact log
- Added delete_entity() and delete_old_entities() functions for cleanup

## [1.2.4] - 2025-11-25

### Changed
- Improved logging to show detailed info about created HA entities
- Now logs each entity name, value, and purpose after update

## [1.2.3] - 2025-11-25

### Fixed
- Fixed Python relative import error by running as module (`python3 -m app.main`)

## [1.2.2] - 2025-11-25

### Fixed
- Fixed config.yaml schema format that broke add-on visibility in Home Assistant store
- Schema now uses proper HA types (str, int, float) instead of invalid name/description objects

## [1.2.1] - 2025-11-25

### Changed
- Version bump to consolidate all v1.2.x changes

## [1.2.0] - 2025-11-25

### Changed
- Export defaults now match import values for Dutch salderingsregeling
  - `export_vat_multiplier`: 1.21 (was 1.0)
  - `export_markup`: 2.48 (was 0.0)
  - `export_energy_tax`: 12.28 (was 0.0)

### Added
- Detailed field descriptions in Home Assistant configuration UI
- Each field now shows name and description explaining its purpose

## [1.1.0] - 2025-11-25

### Changed
- **BREAKING**: Replaced Jinja2 templates with simple numeric configuration fields
  - Removed `import_price_template` and `export_price_template`
  - Added separate fields for VAT, markup, and energy tax (import and export)
- Price calculation now uses formula: `(market_price × vat_multiplier) + markup + energy_tax`
- Configuration is now much easier to edit in Home Assistant UI

### Added
- `import_vat_multiplier`: VAT multiplier for import (default: 1.21 for 21%)
- `import_markup`: Fixed markup in cents/kWh (default: 2.48)
- `import_energy_tax`: Energy tax in cents/kWh (default: 12.28)
- `export_vat_multiplier`: VAT multiplier for export (default: 1.21)
- `export_markup`: Fixed markup for export (default: 2.48)
- `export_energy_tax`: Energy tax for export (default: 12.28)

### Removed
- Jinja2 template dependency (templates replaced by numeric fields)
- `import_price_template` configuration option
- `export_price_template` configuration option

## [1.0.1] - 2025-11-25

### Fixed
- Docker build on Alpine 3.22+ (added `--break-system-packages` for pip)
- Added default BUILD_FROM arg for standalone Dockerfile builds
- Fixed run.sh path to absolute location (/run.sh)

## [1.0.0] - 2025-11-25

### Added
- Initial release of Energy Prices add-on
- Nord Pool API integration for day-ahead electricity prices
- Jinja2 template support for customizable price calculations
- Automatic percentile calculation (P05, P20, P40, P60, P80, P95)
- Price level classification (None/Low/Medium/High)
- Three Home Assistant entities:
  - `sensor.ep_price_import` - Current import price with 48h forecast
  - `sensor.ep_price_export` - Current export price with 48h forecast
  - `sensor.ep_price_level` - Price classification level
- Configurable fetch interval (1-1440 minutes)
- Support for Dutch market (NL delivery area)
- EUR/MWh to cents/kWh conversion with 4 decimal precision
- UTC timestamp handling for DST-safe operation
- Graceful shutdown handling (SIGTERM/SIGINT)
- Comprehensive error handling and logging
- Local testing support via run_local.py

### Configuration Options
- `delivery_area`: Nord Pool delivery area (default: "NL")
- `currency`: Currency code (default: "EUR")
- `timezone`: Display timezone (default: "CET")
- `import_price_template`: Jinja2 template for import price calculation
- `export_price_template`: Jinja2 template for export price calculation
- `fetch_interval_minutes`: Update frequency in minutes (default: 60)

### Technical Details
- Python 3.12+ runtime
- Dependencies: requests>=2.31.0
- Session-based HTTP client with connection pooling
- Linear interpolation for percentile calculations

[1.2.0]: https://github.com/MarkBovee/ha-addons/releases/tag/energy-prices-v1.2.0
[1.1.0]: https://github.com/MarkBovee/ha-addons/releases/tag/energy-prices-v1.1.0
[1.0.1]: https://github.com/MarkBovee/ha-addons/releases/tag/energy-prices-v1.0.1
[1.0.0]: https://github.com/MarkBovee/ha-addons/releases/tag/energy-prices-v1.0.0