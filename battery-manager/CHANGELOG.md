# Changelog

## 0.4.0
- **Entity naming fix**: use `bm_` prefixed object IDs → HA entities are now `sensor.battery_manager_bm_*` (no more doubled `battery_manager_battery_manager` prefix)
- **Rich entity content** (matching legacy NetDaemon quality):
  - **Reasoning**: multi-line "Today's Energy Market" with charging/balancing/profit zones, spread rating, current zone
  - **Forecast**: "Tomorrow's Forecast" with zone ranges, spread, first charge window
  - **Status**: `build_status_message()` — e.g. "Charging Active (8000W) ☀️ 22°C", "Paused | SOC protection (5.0%)"
  - **Price Ranges**: readable display — "Load: €0.231–0.234 | Adaptive: €0.234–0.331 | Discharge: €0.331–0.341"
  - **Current Action**: descriptive state — "Adaptive (discharge to 0W export)", "Charging 8000W"
  - **Charge Schedule**: shows upcoming load-range windows from price curve when no active charge
- **Grid sign convention fix**: standard P1 convention (positive = import, negative = export) across all modules
- **Default grid sensor**: changed from `sensor.battery_api_grid_power` to `sensor.power_usage` (P1 meter)
- **Tests**: 68 tests (up from 52), covering all new text builders

## 0.3.1
- **Bug fix**: Correct grid power sign convention in solar monitor (positive = export, negative = import)

## 0.3.0
- **MQTT Discovery overhaul**: 9 sensors via shared MqttDiscovery (replaces ad-hoc entity publishing)
  - New entities: `bm_charge_schedule`, `bm_discharge_schedule`, `bm_schedule`, `bm_mode`
  - All entities use `unique_id` and grouped under Battery Manager device
- **Passive price range**: wire `charging_price_threshold` as divider — prices below threshold keep battery idle
- **SOC guardian integration**: enforce `can_charge()` / `can_discharge()` checks (respects conservative SOC)
- **Bug fixes**:
  - `gap_scheduler`: return dict instead of JSON string; use UTC timestamps
  - `solar_monitor`: use `get_entity_state()` API; configurable exit threshold; UTC timestamps
  - Replace all deprecated `datetime.utcnow()` with `datetime.now(timezone.utc)`
- **Config**: add `battery_power_entity`, `battery_mode_entity` options
- **Tests**: 52 tests covering price ranges, SOC guardian, gap scheduler, status reporter, solar monitor

## 0.2.1
- Improve operational logging readability (sensors, status, adaptive power)
- Fix confusing 'Reduced' status when idle

## 0.2.0
- Introduce range-based rolling schedule generation
- Add adaptive discharge power adjustments with grace period
- Publish price range, reasoning, and forecast status entities
- Add overnight wait heuristic and scaled power settings
