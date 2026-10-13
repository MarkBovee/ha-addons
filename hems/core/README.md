# hems (core)
Hardware-agnostic planning core for HEMS v2. No Home Assistant imports and no vendor names; vendor and HA
translation lives in adapters outside this package (see docs/hems/intake-decisions.md).

- slots.py      quarter-hour grid on a UTC timeline (DST-safe)
- solar.py      sunrise/sunset without dependencies, for the daylight flag of the solar bonus
- prices.py     import/export price model (settings mirror energy-prices; bonus needs daylight and a positive price), `PriceSeries`
- contracts.py  capability contracts: battery, grid, PV, house load, market prices (units in names, readings with freshness)
- derive.py     vendor-free derivations, e.g. house load from the energy balance
- fakes.py      in-memory implementations of the contracts (battery with losses/limits, frozen sensor) for tests and dry-run
- battery.py    DP planner, rolling horizon, wear margin, hard minimum + reserve floor (per slot), charge->discharge cycle
- balancer.py   priority load balancer, default grid limit 15 kW, hysteresis; uncontrollable loads count first
- forecast.py   median local-hour consumption baseline (datetime-keyed history)
- trace.py      JSONL decision trace

Run: `pip install pytest && pytest`. Test price fixture: `tests/fixtures/quarter_import_prices.csv`
(recorder export of `sensor.current_price`, 3-13 Oct 2026; regenerate with `scripts/hems_collect.py prices`).

Next: replay test on the fixture, rolling-horizon wrapper with trace reasons, then the HA integration shell.
