# Changelog

All notable changes to the HEMS integration. Versions follow `custom_components/hems/manifest.json`.

## [Unreleased]

### Changed
- Panel 0.6.0: the Today, Plan and Devices tabs are one **Overview** (what HEMS does now and the result, a live energy flow
  from solar, grid and battery through the house to the active modules, phase load, weather now and tomorrow, expected solar,
  the next 24 hours per quarter, what is coming up and the devices with their mode) and a **Decisions** tab (every planned
  quarter with its action and the sell, keep and buy values behind it, the timeline, changes and windows). Old links land on the
  new tabs.
- The Open-Meteo request also asks for the hourly weather code, cloud cover, daylight and precipitation. The panel's weather
  (now and tomorrow) comes from that, not from a Home Assistant weather entity: Buienradar reported "sunny" at night.
- While tomorrow's prices are unknown, the battery is filled to 100 % in the day's cheapest quarters before today's most expensive
  quarter; after that peak the plan decides freely (no forced refill at night). Once tomorrow's prices are known, no target applies.
- Energy kept past the horizon is valued from the last 7 days of Nord Pool prices (typical peak, never below the typical refill
  price), fetched once a day, instead of today's cheapest price.
- The sell limit (`max_sell_hours`) applies per sell window (a run of quarters above the day's median export price), not per day:
  a morning and an evening peak may each sell.
- The sell limit is set in quarters of 15 minutes per sell window (`max_sell_quarters`, 0 = no limit) instead of hours. An entry that
  still has `max_sell_hours` keeps its limit (1 hour = 4 quarters) until the setting is saved again.
- Tomorrow's Nord Pool prices are asked for from 12:30 (published around 12:45) instead of 13:00, so the plan picks them up sooner.

### Added
- Write lock per module (`advice.WRITE_UNLOCKED_MODULES`, still empty): a module whose lock is open offers `auto` in its mode select.
- HEMS clears the SAJ slots it wrote (masks and mode first, then every slot; Self-consumption) when the battery leaves auto, the
  master switch goes off, on `hems.disarm_all` and on unload. Whether HEMS's slots are on the inverter is stored, so slots left
  behind by a restart are cleared on the first cycle; slots HEMS never wrote (battery-manager's) are not touched.
- A failing SAJ write round is logged and no longer stops the cycle.
- Own grid-follow on discharge slot 7 (battery-manager's adaptive control): every 60 s, outside the planned charge and sale
  slots, its power is stepped on the meter so the grid stays at 0 W; it spans two quarters and moves on per quarter, and is
  cleared inside a planned slot or at the SoC floor. Only in auto with the master on; it shares the SAJ lock with the write round.
- Spa (external control) learns its energy per day from the measured load, recent days weighing most (an existing setup's
  forecast moves from the configured kWh to the learned value; `spa_daily_kwh` is the start value).
- The battery's round-trip efficiency is learned from its charged and discharged energy and the SoC change over the history
  window (`round_trip_eff` is the start value and the fallback for too little or implausible data).
- Optional role `water_heater_energy_entity` (the heater's own energy meter): the heater comes out of the load history hour by
  hour, and the night, day and legionella run energies are learned from it (median normal day, legionella-day mean).
- What HEMS learned, next to the configured values, in the `learned` attribute of the status sensor.
- Sell floor minimum per weekday (`reserve_soc_<day>_pct`, 0 = the general minimum).
- Spa module (off by default): keeps the water in a temperature band, heats in cheap quarters or on solar surplus, gives way first on
  a full phase; `sensor.hems_spa_target`, `select.hems_spa_mode`, roles `spa_climate_entity` and `spa_power_entity`. The writer
  (`climate.set_temperature`) is behind the phase lock.
- Battery setting `max_soc_pct` (charge ceiling, default 99 %): the planner never charges above it; it never drops below the sell floor maximum.

### Fixed
- The settings form could not be saved ("Not all required fields are filled in"): an empty EV deadline or net-metering end date was a
  required field. Those fields are optional now; leaving one empty stores it empty.

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
