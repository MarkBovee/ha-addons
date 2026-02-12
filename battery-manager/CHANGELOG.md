# Changelog

## 0.8.7
- **Fix: Schedule part 2 guard** — Ensure `schedule_part_2` is always defined so schedule publishing does not crash after entity name changes.

## 0.8.6
- **Fix: Entity naming** — Corrected entity object_ids to match actual Home Assistant entities. Changed from `bm_*` prefix to direct names (`schedule_part_2` instead of `bm_schedule_2`) to fix issue where `sensor.battery_manager_schedule_part_2` wasn't being populated correctly.

## 0.8.5
- **Feature: Split schedule entity** — Added `sensor.bm_schedule_2` to handle markdown table overflow. When the combined schedule table exceeds 255 characters, it is split across `sensor.bm_schedule` (first 255 chars) and `sensor.bm_schedule_2` (remaining text). The full table remains available in the `markdown` attribute of `sensor.bm_schedule`.
- **Fix: Import error** — Resolved `NameError` for `ENTITY_SCHEDULE_2` in the main loop.

## 0.8.4
- **Fix: Timezone handling** — Status messages now display local time instead of UTC in "Now" and schedule windows
- **Fix: Entity state limits** — Detect long schedule tables (>255 chars) and summarize state (e.g., "3 charge windows") while keeping full markdown table in attributes. Prevents "unknown" entity states.

## 0.8.3
- **Feature: Optional Adaptive Power** — Added `adaptive` config section to enable/disable adaptive power logic. When disabled, battery remains passive (idle) between charge/discharge windows instead of adaptively discharging.

## 0.8.2
- **Fix: Adaptive timing stability** — Keep original schedule times when adjusting power, only change the power value. Prevents inverter toggling caused by re-clipping start times every monitor cycle
- **Fix: Reduce discharge stability** — Same approach: keep original times, only halve power
- **Cleanup** — Removed `_round_up_five_minutes()` and `_remaining_minutes()` helpers (no longer needed)

## 0.8.1
- **Fix: Status display** — `ENTITY_CURRENT_ACTION` now reflects actual battery state (charging/discharging/idle) instead of only the price range at schedule generation time
- **Fix: Adaptive discharge timing** — Power adjustments now clip start times to current time with remaining duration, preventing stale timestamps being sent to battery-api
- **Fix: Reduce discharge timing** — Same start-time clipping applied when reducing discharge for grid export protection
- **Logging cleanup** — Consolidated sensor data into single line (SOC, Grid, Solar, Load, Bat, EV), removed duplicate EV sensor log, demoted monitoring header to debug level

## 0.8.0
- **Multi-period scheduling**: Send ALL upcoming charge/discharge/adaptive windows to battery-api at once (was single-interval)
  - Charge windows limited to 3 periods, discharge+adaptive limited to 6 periods (SAJ API constraints)
  - Eliminates dependency on hourly MQTT reconnection for schedule continuity
- **MQTT retry**: `_publish_schedule()` retries 3 times with 5s wait between attempts, checks `is_connected()` before each
- **Adaptive discharge**: Gaps between charge and discharge windows now scheduled as adaptive discharge (min power)
  - Monitoring loop adjusts power dynamically to target 0W grid export
  - Classified as prices above `charging_price_threshold` but below discharge range
- **Passive/Balancing split**: Status display splits adaptive range into two lines when threshold is configured
  - 💤 Passive: prices below `charging_price_threshold` (battery idle)
  - ⚖️ Balancing: prices at/above threshold (adaptive discharge active)
- **Log retention**: Rotating file handler writes to `/data/logs/` (2MB × 3 backups = 8MB total)
- **Tests**: 101 tests (up from 93), covering adaptive windows, Passive/Balancing split, and price range display

## 0.7.1
- **Profit summary**: Today and tomorrow forecasts show "💵 Profit: €X–€Y/kWh" with min–max arbitrage range when discharge is profitable
- Renamed discharge price line from "Profit" to "Selling" for clarity

## 0.7.0
- **Per-day schedule ranges**: Tomorrow's charge/discharge windows use tomorrow's calculated ranges, not today's
  - Fixes: today's cheaper prices no longer squeeze out tomorrow's charge hours
  - Respects `top_x_charge_hours` per day (e.g. 3 hours today AND 3 hours tomorrow)
- **Day labels in schedule**: "Tomorrow" header shown in schedule entities when prices span two days
- **Tests**: 93 tests (up from 89), covering per-day range logic and day labels

## 0.6.0
- **Full-day schedule display**: Past windows from today now shown (marked ✅) instead of disappearing after they pass
- **Informative combined schedule**: Shows no-discharge reason in combined schedule entity when spread is too small
- **Tomorrow price detection**: When tomorrow's prices arrive (~14:00), schedule regenerates immediately instead of waiting for next hourly cycle
- **Tests**: 89 tests (up from 87), covering past window inclusion and yesterday exclusion

## 0.5.1
- **Invalid spread handling**: When profit margin is too small (discharge_min > discharge_max), discharge_range returns None instead of invalid range
- **Informative messages**: Discharge schedule shows helpful message when no profitable windows exist
  - Example: `📉 No profitable discharge today (spread €0.062 < €0.10 minimum)`
- **Tests**: 87 tests (up from 83), covering invalid spread cases and no-range messages

## 0.5.0
- **Schedule entities populated**: Scan full price curve to find all upcoming charge/discharge windows
  - **Charge Schedule**: shows all upcoming load-range windows with times, power, avg price (e.g. `⚡ 00:00–05:00 8000W (€0.232)`)
  - **Discharge Schedule**: shows all upcoming profit-range windows (e.g. `💰 17:00–19:00 6000W (€0.380)`)
  - **Schedule**: combined markdown table with both, sorted by time, marked active (🔴), done (✅), or upcoming (⏰)
- **Window grouping**: consecutive hourly slots grouped into windows with averaged prices
- **Tests**: 83 tests (up from 68), covering window-finding, grouping, and display logic

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
