# Changelog

All notable changes to the Energy Prices add-on will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.5.1] - 2026-01-01

### Added
- **Detailed Logging**: Added logging of sunrise/sunset times and a detailed price schedule table showing spot, import, export, daylight status, and bonus application for each interval.

## [1.5.0] - 2026-01-01

### Added
- **Zonneplan 2026 Pricing Support**: Implemented new pricing logic for Zonneplan dynamic contracts effective Jan 1, 2026.
- **Solar Bonus**: Added support for calculating solar bonus (+10%) during daylight hours on positive spot prices.
- **Daylight Calculation**: Added `astral` library to accurately determine daylight hours based on configured location.
- **New Configuration Options**:
  - `export_fixed_bonus`: Fixed bonus per kWh for export (default €0.02).
  - `export_bonus_pct`: Solar bonus percentage (default 10%).
  - `latitude` / `longitude`: Location for daylight calculations (default: Utrecht).

### Changed
- **Import Formula**: Updated to `(spot + markup + tax) * vat` to match Zonneplan 2026 model.
- **Export Formula**: Updated to include fixed bonus and conditional solar bonus, with VAT applied to the total (netting).
- **Defaults**: Updated default markup and tax values to match Zonneplan 2026 rates.

## [1.4.0] - 2025-12-05

### Added
- **New statistics sensors** for today's prices:
  - `sensor.energy_prices_average_price` - Average price for today
  - `sensor.energy_prices_minimum_price` - Lowest price today
  - `sensor.energy_prices_maximum_price` - Highest price today
  - `sensor.energy_prices_max_profit_today` - Price spread (max - min) for arbitrage potential
- **Tomorrow availability binary sensor**:
  - `binary_sensor.energy_prices_tomorrow_available` - ON when tomorrow's prices are published (typically after 13:00 CET)
  - Includes `tomorrow_intervals` attribute showing count of available intervals

### Changed
- Price statistics (min, max, avg) now calculated only from today's prices for accuracy
- Enhanced logging with today's statistics summary

## [1.3.4] - 2025-11-26

### Changed
- Refactored to use shared modules (`shared/addon_base.py`, `shared/ha_api.py`, etc.)
- Migrated from global `shutdown_flag` to `threading.Event` pattern for cleaner shutdown handling
- Consolidated Home Assistant API code into reusable `HomeAssistantApi` class
- Configuration loading now uses `load_addon_config()` from shared modules

## [1.3.3] - 2025-11-26

### Fixed
- Fixed `UnboundLocalError` in `load_config()` when config file exists - JSON config was not being loaded from `/data/options.json`

## [1.3.2] - 2025-11-25

### Added
- MQTT credentials now configurable in add-on UI (`mqtt_user`, `mqtt_password`)
- Default MQTT settings exposed: `mqtt_host: core-mosquitto`, `mqtt_port: 1883`

### Fixed
- Logging now shows full precision for markup and tax values (0.0248 instead of 0.02)

## [1.3.1] - 2025-11-25

### Changed
- **Unit changed from cents/kWh to EUR/kWh** for consistency with HA energy dashboard
- Configuration values (markup, energy_tax) now in EUR instead of cents
- Default values: `import_markup: 0.0248`, `import_energy_tax: 0.1228` (was 2.48 and 12.28)

### Fixed
- Updated MQTT callbacks for paho-mqtt 2.x API compatibility

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