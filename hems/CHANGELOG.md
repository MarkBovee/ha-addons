# Changelog

All notable changes to the HEMS integration. Versions follow `custom_components/hems/manifest.json`.

## [0.2.0] - 2026-10-29

### Added
- Brand images (icon, logo, dark variants) in `custom_components/hems/brand/`, shown by Home Assistant 2026.3 and later.
- Water heater executor in advisory: the water heater add-on's rules (negative price, away, bath, night, legionella, day run,
  stand-by, cycle gap) with every temperature a setting; `sensor.hems_water_heater_target`; away and bath roles.
- Own legionella record from the tank temperature (`sensor.hems_last_legionella`); the legionella run is planned only when it is
  due, counted in calendar days.
- kWh counters for solar and battery in and out, and `hems.setup_energy_dashboard`.
- SAJ write layer behind a phase lock: slot builder, battery-api's write protocol with verify and retry, own grid-follow,
  `sensor.hems_battery_schedule` and "Would write" in the panel; watchdog automation.
- Insights per day, week, month and year, the stored-energy value and a rest-of-day forecast.
- Sidebar panel with Today, Plan, Devices and Insights, and a kiosk view.

### Changed
- The battery reserve is a sell floor: below it the battery covers the house (self-consumption) down to the hard minimum, and the
  floor follows the expected use (30–60 %).

## [0.1.0] - 2026-10-13

### Added
- Dry-run battery planner, Nord Pool prices, solar and load forecasts, EV planner, decision trace.
