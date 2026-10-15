## Why

Solar-aware charge planning spreads the grid share of the charge deficit evenly over the charge window and expects PV on top. Real PV peaks around noon, so the battery receives planned grid power plus a large live solar share, fills before the window ends, and the cheap grid energy bought early is partly wasted. The plan is only re-evaluated hourly.

## What Changes

- While a solar-aware charge window is active, `battery-manager` trims the published grid charge power every monitor cycle: required charge rate (remaining deficit over remaining charge-window hours) minus live solar surplus, plus a 1000 W buffer, rounded down to a 1000 W step and clamped between 0 W and the planned ceiling.
- A trimmed schedule is only republished when the step changes, with a minimum interval between publishes.
- New options under `solar_aware_charging`: `live_trim_enabled` (default true), `live_trim_buffer_w` (default 1000), `live_trim_step_w` (default 1000).
- Negative-price windows and windows that are not solar-aware are never trimmed.

## Capabilities

### New Capabilities
- `live-solar-charge-trim`: Live adjustment of grid charge power during a solar-aware charge window based on current solar surplus.

### Modified Capabilities

None.

## Impact

- `battery-manager/app/solar_charge_optimizer.py`, `battery-manager/app/main.py`, `battery-manager/config.yaml`, `battery-manager/CHANGELOG.md`
- No new entities and no change to the battery-api schedule payload format. Home Assistant remains the only integration boundary.
