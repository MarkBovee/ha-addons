# hems (core)
Hardware-agnostic planning core for HEMS v2. No Home Assistant imports and no vendor names; vendor and HA
translation lives in adapters outside this package (see docs/hems/intake-decisions.md).

- slots.py      quarter-hour grid on a UTC timeline (DST-safe)
- solar.py      sunrise/sunset without dependencies, for the daylight flag of the solar bonus
- prices.py     import/export price model (settings mirror energy-prices; bonus needs daylight and a positive price), `PriceSeries`
- contracts.py  capability contracts: battery, grid, PV, house load, market prices (units in names, readings with freshness)
- derive.py     vendor-free derivations, e.g. house load from the energy balance
- fakes.py      in-memory implementations of the contracts (battery with losses/limits, frozen sensor) for tests and dry-run
- rolling.py    rolling-horizon step: plan to the end of the known prices, execute one quarter, log plan shifts
- replay.py     replay recorded days through the rolling planner and account them like the recorded battery
- dryrun.py     dry-run engine: inputs (prices, history, weather, SoC) to a decision plus a status that says why not
- pvforecast.py PV forecast from irradiance (one fitted gain, inverter clip); weather.py Open-Meteo parsing
- battery.py    DP planner, rolling horizon, wear margin, hard minimum + reserve floor (per slot), charge->discharge cycle
- balancer.py   priority load balancer, default grid limit 15 kW, hysteresis; uncontrollable loads count first
- forecast.py   median local-hour consumption baseline (datetime-keyed history)
- trace.py      JSONL decision trace (injectable clock, size rotation); the planner supplies a reason per slot

Run: `pip install pytest && pytest`. Test price fixture: `tests/fixtures/quarter_import_prices.csv`
(recorder export of `sensor.current_price`, 3-13 Oct 2026; regenerate with `scripts/hems_collect.py prices`).

HA integration (dry-run): custom_components/hems, see docs/hems/install.md. After changing this package run scripts/sync_hems_core.py.
