# Changelog

All notable changes to the Energy Prices add-on will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
- Dependencies: requests>=2.31.0, Jinja2>=3.1.0
- Sandboxed Jinja2 environment for template security
- Session-based HTTP client with connection pooling
- Fail-fast template validation at startup
- Linear interpolation for percentile calculations

[1.0.0]: https://github.com/MarkBovee/ha-addons/releases/tag/energy-prices-v1.0.0
