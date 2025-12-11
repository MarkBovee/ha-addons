## Version: 2.3

## Why
- Provide a Home Energy Management System add-on focused on battery control using the proven Range-Based strategy from NetDaemon.
- Consolidate price-aware scheduling into a single add-on that depends on the existing `energy-prices` add-on for prices and the `battery-api` add-on for schedule application.
- Remove EMS toggling complexity; make opportunistic solar optional and configurable.

## What Changes
- Add new `hems` add-on that implements rolling 15-minute Range-Based scheduling with 1-minute adaptive monitoring and 15-minute status refresh.
- Fixed price source set to `sensor.energy_prices_electricity_import_price`; no external price fallback.
- Configurable inverter/power/SOC limits, TopX ranges, adaptive thresholds, optional temperature-based discharge, and optional opportunistic solar integration.
- Expose HA entities for status/next periods/adaptive power via REST/MQTT using shared helpers.

## Impact
- New capability: `hems` add-on (depends on `battery-api` and `energy-prices`).
- Documentation: new `hems/README.md`.
- No EMS toggle support; EMS configuration intentionally excluded.

## Status
- 100% (implemented and documented)
