# Changelog

## 0.8.44 — 2026-03-10
- **Breaking change: Config rename** — replaced `heuristics.charging_price_threshold` with `heuristics.adaptive_price_threshold` to match what the threshold actually controls.
- **Breaking change: Runtime power sensor rename** — replaced `sensor.battery_manager_last_commanded_power` with `sensor.battery_manager_effective_discharge_power`, which now reflects the live effective discharge power and exposes `active_window_type` metadata.
- **Tests/docs:** Updated battery-manager tests and documentation for the renamed threshold and runtime power sensor.

## 0.8.43 — 2026-03-10
- **Fix: Adaptive runtime state tracking** — monitor logic now follows the last published schedule, so conservative-SOC adaptive overrides keep reporting `adaptive` instead of falling back to stale passive/discharge state.
- **Fix: Adaptive power visibility** — current action and mode now reflect the active published adaptive window power, preventing `Adaptive (no active window)` when adaptive discharge is actually running.
- **Tests:** Added regressions for published adaptive override tracking and adaptive mode reporting.

## 0.8.42 — 2026-03-09
- **Feature: Fractional temperature discharge durations** — `temperature_based_discharge.thresholds[].discharge_hours` now accepts decimals and preserves them through slot counting, so 15/30-minute schedules can target the intended discharge duration.
- **Fix: Exact profitable discharge slot selection** — discharge windows are now built from the exact top-priced profitable export slots instead of every interval inside the broad discharge price band.
- **Feature: Max-SOC stabilizer** — when SOC reaches `soc.max_soc`, Battery Manager now publishes a 5-minute discharge burst at 50% of configured max discharge power to keep SOC hovering around the ceiling.
- **Docs:** Updated config/README notes for decimal `discharge_hours` and max-SOC stabilizer behavior.

## 0.8.41 — 2026-03-09
- **Fix: SOC protection hardening** — Added SOC freshness guard (`timing.max_soc_sensor_age_seconds`, default 900s). Active discharge now enters a protective pause when SOC is unavailable/stale to prevent uncontrolled drain.
- **Fix: Sell-wait observability** — `_get_sell_wait_decision` now emits structured diagnostics for skipped decisions (`disabled`, `invalid_horizon`, `no_target_window_candidate`, `no_pre_target_windows`, `gain_below_threshold`) and schedule generation logs the exact skip reason.
- **Config tuning: Morning deferral defaults** — Updated defaults to better support next-morning postponement: `sell_wait_horizon_hours: 20`, `sell_wait_min_gain_threshold: 0.02`, `sell_wait_morning_start_hour: 0`, `sell_wait_morning_end_hour: 10`.
- **Fix: Config typo** — Corrected `soc.conservative_soc` default to `40` in `config.yaml`.
- **Tests:** Added regressions for sell-wait diagnostics and protective pause when SOC is unavailable.

## 0.8.40 — 2026-03-08
- **Feature: Deferred morning sell heuristic** — Added optional logic to delay discharge when a better sell window exists within a configurable look-ahead horizon (default 12h) and preferred morning window.
- **Config: New heuristic options** — Added `sell_wait_for_better_morning_enabled`, `sell_wait_horizon_hours`, `sell_wait_min_gain_threshold`, `sell_wait_morning_start_hour`, and `sell_wait_morning_end_hour`.
- **Tests:** Added focused unit tests for sell-wait decision boundaries and horizon handling.

## 0.8.39 — 2026-03-07
- **Release: Repository-wide add-on bump** — Version bump for coordinated all-addon release.
- **Note:** Runtime behavior unchanged from 0.8.38.

## 0.8.38 — 2026-03-07
- **Fix: Adaptive publish log clarity** — Schedule publish log now includes adaptive discharge context and commanded wattage when adaptive periods are present.
- **Fix: Current action in adaptive override** — `sensor.battery_manager_current_action` is now updated during reduced/adaptive override with explicit `Adaptive Discharging {W}W` state.
- **Refactor: Main/status reporter cleanup** — Extracted duplicated range/state publishing, sensor snapshot logging, active-period power lookup, and datetime parsing helpers to reduce complexity without behavior changes.

## 0.8.37 — 2026-03-07
- **Fix: Reduced-mode adaptive power response** — When low-SOC conservative protection downgrades an active discharge window to adaptive mode, runtime now calculates and publishes adaptive power from live grid conditions instead of staying at static min/0W. This restores real adaptive behavior above `charging_price_threshold` during reduced mode.

## 0.8.36 — 2026-03-05
- **Fix: Combined schedule table source** — `Battery Charging Schedule` table now renders from the generated/published schedule payload instead of full-day candidate windows. This keeps the table aligned with actual scheduled periods and prevents past/non-selected windows from appearing as if they are active plan entries.

## 0.8.35 — 2026-03-05
- **Fix: Discharge window priority in schema** — When building capped discharge periods for battery-api, profitable `discharge` windows are now selected before `adaptive` windows. This prevents adaptive filler periods from hiding expected high-price sell windows in the generated schedule.

## 0.8.34 — 2026-03-05
- **Fix: Conservative SOC runtime downgrade** — During active discharge at or below `soc.conservative_soc`, the active window is now downgraded to adaptive/min-power behavior instead of continuing aggressive discharge.
- **Fix: Today-only schedule range calculation** — Today's load/discharge/adaptive ranges and rank-based power now use only today's price points, preventing tomorrow prices from distorting today's sell windows in schedule text.
- **Fix: Sell-buffer floor precharge trigger** — If SOC drops below `soc.sell_buffer_min_soc`, precharge is now allowed even when current price is above the normal precharge ceiling so buffer recovery is not skipped.

## 0.8.33 — 2026-03-04
- **Release bump:** Published current validated baseline with schedule display integrity fixes retained.
- **Note:** No additional date/time classification changes in this release.

## 0.8.32 — 2026-03-04
- **Fix: Schedule table integrity** — Split long combined schedule state on line boundaries to avoid broken/truncated markdown rows in Home Assistant.
- **Fix: Displayed power values in combined schedule** — Use explicit display powers so discharge windows no longer appear as `0W` when runtime adaptive power is low.

## 0.8.31 — 2026-03-04
- **Rollback: UTC day-split logic** — Reverted the 0.8.30 local/UTC day-splitting runtime change after field validation showed scheduling side effects.
- **Note:** Runtime behavior is restored to pre-0.8.30 scheduling logic so current production behavior can be re-verified.

## 0.8.29 — 2026-03-02
- **Change: Remove High Grid Export reduction** — Grid-export based discharge throttling has been removed from monitor logic.
- **Change: Reduced mode only on low SOC** — `Reduced` now applies only when an active discharge window runs at or below `soc.conservative_soc`.
- **Fix: Reduced override recovery** — When low-SOC reduction clears, the generated schedule is force-restored so discharge power returns to planned values.

## 0.8.28 — 2026-03-02
- **Fix: Passive Solar republish loop** — Passive Solar now publishes its gap schedule only when the mode transitions to active, instead of re-publishing a fresh timestamped payload every monitor cycle.
- **Fix: Passive Solar exit recovery** — When passive mode clears, battery-manager force-publishes the normal generated schedule so control returns cleanly to planned windows.
- **Fix: Short passive fallback window** — Passive-gap safety discharge fallback duration is now 1 minute to avoid long unintended discharge windows.

## 0.8.27 — 2026-02-26
- **Fix: Startup crash in schedule generation** — Resolved `UnboundLocalError` where `upcoming_windows` could be referenced before assignment during discharge window ranking. The ranking step now runs after upcoming windows are calculated.

## 0.8.26 — 2026-02-24
- **Fix: Discharge slot power stability** — Explicit `discharge` windows now keep their scheduled power during monitor ticks; runtime adaptive power recalculation is limited to `adaptive` windows only.
- **Fix: Stable per-window discharge ranking** — Schedule generation now ranks each discharge window individually by price (with deterministic tie-break), so hourly schedule regeneration does not reshuffle same-day slot power when prices are unchanged.

## 0.8.25 — 2026-02-24
- **Fix: Passive Solar false activation** — Require minimum solar generation to enter passive mode; passive mode now only activates when `grid_power < -entry_threshold` and `solar_power >= passive_solar.min_solar_entry_power`.
- **Fix: Sell-buffer protection in sell windows** — During active sell windows, SOC below `conservative_soc` now downgrades runtime mode to `adaptive` instead of hard-pausing discharge; sell-buffer floor is enforced only outside sell-mode to preserve planned precharge behavior.
- **Config: `passive_solar.min_solar_entry_power`** — New option to set minimum PV generation required to consider passive solar activation (default 200W).
- **Tests:** Added targeted unit test to prevent passive-solar false positives.

## 0.8.24
- **Fix: Sell-buffer timing gate** — Dynamic sell-buffer SOC/precharge now activates only within a configurable lead window before the first planned sell/discharge period (`soc.sell_buffer_activation_hours_before_sell`, default 3h), instead of reacting all day.

## 0.8.23
- **Fix: Precharge price safety** — Dynamic sell-buffer precharge is now blocked when current import price is above the configured charging threshold (fallback: load-range max), preventing high-price emergency charging windows.

## 0.8.22
- **Fix: Schedule logging clarity** — Schedule summaries now clearly separate internal windows from API local-day payload counts.
- **Fix: Window type visibility** — Logged schedule lines now tag each period as `charge`, `discharge`, `adaptive`, or `precharge`, with source price shown when available.

## 0.8.21
- **Feature: 10% sell-buffer rounding** — Dynamic sell-buffer SOC is now rounded to configurable 10% steps by default (`soc.sell_buffer_rounding_step_pct: 10`), matching practical targets like 50% for 1h and 80% for 2h.

## 0.8.20
- **Feature: Dynamic pre-sell SOC buffer** — Added sell-buffer SOC calculation based on planned discharge hours before the first main charge window.
- **Feature: Automatic pre-charge for buffer** — When SOC is below required sell-buffer target, battery-manager schedules an early 8000W pre-charge window to rebuild reserve.
- **Feature: Runtime SOC protection update** — Active discharge now respects dynamic sell-buffer SOC floor in addition to existing minimum SOC and conservative rules.
- **Config: New SOC options** — Added `soc.battery_capacity_kwh`, `soc.sell_buffer_enabled`, and `soc.sell_buffer_min_soc`.

## 0.8.19
- **Fix: SAJ schedule overlap prevention** — When publishing to `battery-api`, only local-today windows are sent and duplicate/overlapping `HH:MM` periods are sanitized. This prevents collisions like `discharge[0]` vs `discharge[4]` at the same clock time when tomorrow windows exist.

## 0.8.18
- **Fix: Adaptive export hang** — Allow adaptive discharge to manage grid export instead of forcing reduced discharge in adaptive mode.

## 0.8.17
- **Feature: Last commanded power sensor** — Expose the last commanded adaptive discharge power as a MQTT Discovery sensor for dashboard visibility.

## 0.8.16
- **Fix: Adaptive power oscillation** — Fixed adaptive power calculation that was using lagging battery sensor value instead of the last commanded power, causing overshoot and oscillation between high grid export/import. Now tracks commanded power in state and uses it as baseline for subsequent adjustments.

## 0.8.15
- **Fix: Monitor log clutter** — Reduce `battery-manager` log noise by suppressing identical status messages. "Monitor Status" is now only logged when the state or reason changes.
- **Fix: Redundant schedule updates** — Prevent sending duplicate schedule payloads to `battery-api` if the schedule has not changed, reducing MQTT traffic.


## 0.8.14
- **Fix: Entity Naming (final)** — Add explicit `object_id` with addon prefix to all MQTT discovery payloads. Without this field, HA generates generic entity IDs like `sensor.status` instead of `sensor.battery_manager_status`. Applied to all entity types (sensor, number, select, button, text) in the shared module. Existing entities for other addons are unaffected (HA preserves entity IDs by unique_id).

## 0.8.13
- **Fix: Entity Naming (root cause)** — Reverted incorrect `object_id` override in shared MQTT discovery module. Entity IDs are now derived by Home Assistant from device name + entity name, producing correct IDs like `sensor.battery_manager_status`. Previous fix attempts (0.8.8–0.8.12) added an explicit `object_id` field to the MQTT discovery payload which could cause naming conflicts across addons. All existing broken entities must be cleaned before this update.

## 0.8.12
- **Fix: Entity Naming** — Restore `battery_manager_` prefix to entity IDs to fix "No Prefix" issue (e.g. `sensor.status` -> `sensor.battery_manager_status`). Includes safety check to prevent double-prefixing.

## 0.8.11
- **Fix: Entity Naming** — Force explicit `object_id` in MQTT discovery payload to prevent duplicate prefixes (e.g. `battery_manager_battery_manager_...`).

## 0.8.8
- **Fix: Mode entity** — Correctly update `sensor.battery_manager_mode` with active price range ("load", "discharge", "adaptive", "passive").
- **Fix: Entity cleanup** — Cleaned up legacy MQTT discovery topics to prevent duplicate Entities.

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
