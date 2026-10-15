## Why

Observed on 2026-10-07/08: only one hour was sold at a ~0.47 evening peak while the battery stayed at 52% SoC, the night was grid-charged at margins below `min_profit_threshold` once the ~10% round-trip loss counts, planned midday charge power jumped between 500 W and 8000 W from one regeneration to the next, and the schedule was re-published every minute. The add-on log keeps about an hour, so the cause of each decision could not be reconstructed.

`battery-manager` is replaced by HEMS v2 later but must stay usable until then, so the changes are small and local.

## What Changes

- Decision trace: one JSON line per plan generation in `/data/decision_trace.jsonl` (rotated), last record on `sensor.battery_manager_decision`, one INFO line, and a log of >25% planned-power changes with the inputs that moved.
- Sell-window feasibility uses the SoC projected at each window start, including the forecast PV share of solar-aware charge windows.
- Equal-priced sell quarters resolve to the earliest quarter (contiguous blocks).
- Grid charging outside the strict top-X cheapest slots (spread-only windows, sell-buffer precharge) needs `sell * round_trip_efficiency - charge >= grid_charge_min_margin`. Options `heuristics.grid_charge_min_margin` (default `min_profit_threshold`), `heuristics.round_trip_efficiency` (default 0.90).
- Option `heuristics.margin_basis: day_min_import | solar_export` (default `day_min_import`, unchanged).
- Option `heuristics.discharge_after_charge_only` (default `true`): top-X sell hours are chosen only from quarters after the main charge window of that day. **BREAKING (behaviour)**: a morning peak before the charge window is no longer a scheduled sell window and no longer triggers precharging; set the option to `false` for the previous whole-day ranking.
- Charge window power is held for one hour unless SoC deviates >5 pp from the projection or the remaining-solar forecast moves >25% beyond normal depletion.
- The schedule is sent to battery-api only when the published periods change (adaptive power steps below 100 W ignored), plus an hourly heartbeat.

## Capabilities

### New Capabilities
- `battery-manager-decisions`: Explainable, margin-aware, stable sell/charge planning for battery-manager.

### Modified Capabilities

None.

## Impact

- `battery-manager/app/main.py`, `price_analyzer.py`, new `margin.py`, `plan_stability.py`, `decision_trace.py`, `status_reporter.py`, `config.yaml`, README, CHANGELOG, tests.
- One new sensor (`sensor.battery_manager_decision`). `battery-api` and its payload format are untouched. Home Assistant remains the only integration boundary.
