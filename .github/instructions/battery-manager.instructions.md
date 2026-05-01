---
applyTo: 'battery-manager/**'
---

# Battery Manager — Agent Instructions

Addon-specific conventions and architecture rules for `battery-manager/`.  
**Keep this file up to date after every change to the addon.**

---

## Purpose

Optimizes battery charge/discharge scheduling using Nord Pool electricity prices, solar forecast, grid power, SOC, and EV charging state. Publishes a multi-period schedule to `battery-api` via MQTT.

---

## Module Responsibilities

| File | Role |
|------|------|
| `app/main.py` | Orchestration: `generate_schedule()` + `monitor_loop()`. All cross-cutting logic lives here. |
| `app/price_analyzer.py` | Price curve analysis: top-X selection, range calculation, interval detection, `get_current_price_entry()` |
| `app/status_reporter.py` | Entity publishing, `find_upcoming_windows()`, display text builders |
| `app/schedule_builder.py` | Builds charge/discharge schedule lists from periods |
| `app/solar_charge_optimizer.py` | Solar-aware charge allocation: reduces grid charge when PV will cover the deficit |
| `app/solar_monitor.py` | Passive Solar mode: detect excess PV and suppress battery discharge |
| `app/gap_scheduler.py` | Generates the Passive Solar gap schedule (0W charge slot) |
| `app/grid_monitor.py` | Detects grid export / over-discharge; triggers adaptive power reduction |
| `app/soc_guardian.py` | `can_charge()`, `can_discharge()`, sell-buffer SOC calculation |
| `app/temperature_advisor.py` | Maps temperature → discharge hours via threshold config |
| `app/ev_charger_monitor.py` | `should_pause_discharge()` — pauses discharge when EV is charging |
| `app/power_calculator.py` | `calculate_rank_scaled_power()` — rank-based power scaling across discharge windows |
| `app/models.py` | Data models (add if introduced) |

---

## Two-Loop Architecture

The addon runs two separate loops:

1. **`generate_schedule()`** — Called on startup and every `update_interval` (default 1h).  
   Fetches fresh price curves, calculates ranges, builds the full multi-period schedule, and publishes it to battery-api via MQTT. Also triggers on price curve growth (tomorrow prices).

2. **`monitor_loop()`** — Called every `monitor_interval` (default 60s).  
   Reads live sensor values (SOC, grid power, EV power), checks active schedule periods, adjusts discharge power adaptively, handles Passive Solar, EV pause, SOC protection, and max-SOC stabilizer.

**Key rule:** `generate_schedule()` may be triggered from inside `monitor_loop()` when a live price band has no active window (rolling schedule regen).

---

## Price Range Semantics

Four mutually exclusive market bands per interval:

| Band | Condition | Battery action |
|------|-----------|---------------|
| `load` | Import price in cheapest top-X | Charge at scheduled power |
| `discharge` | Export price in highest top-X + above min_profit | Discharge at rank-scaled power |
| `adaptive` | Above `adaptive_price_threshold`, not in load/discharge | Discharge to hold grid ≈ 0W |
| `passive` | Below `adaptive_price_threshold` | Battery idle |

**Critical distinctions (do not blur):**
- `price_range` is the market classification of the current interval.
- `mode` / `current_action` entities SHALL only show `adaptive` when the adaptive discharge control loop is *actively running* (not when the price band is adaptive but the battery is waiting).
- When no charge/discharge window is active and price is passive/adaptive-idle, report `idle` or `passive` and include the next scheduled event.

---

## Schedule Period Schema

Every charge and discharge period in the schedule dict:

```python
{
    "start": "<ISO timestamp>",      # UTC ISO string
    "power": <int watts>,
    "duration": <int minutes>,
    "window_type": "<str>",          # see below
    "price": <float>,                # €/kWh at that slot
}
```

### `window_type` values

| Value | Meaning |
|-------|---------|
| `charge` | Regular price-based charge window |
| `precharge` | Emergency pre-sell buffer charge |
| `negative_price_charge` | Charge at max power during negative import prices (grid pays to consume) |
| `discharge` | Profitable sell window |
| `adaptive` | Adaptive discharge (grid → 0W) |
| `max_soc_stabilizer` | Short discharge burst at max SOC |
| `passive_gap` | Passive Solar gap slot (0W charge) |

---

## Hard Limits

```python
MAX_CHARGE_PERIODS = 3      # SAJ inverter API limit
MAX_DISCHARGE_PERIODS = 6   # SAJ inverter API limit
```

Discharge windows are prioritized: profitable sell windows fill slots first, adaptive windows fill remaining slots.

---

## Window Selection Pipeline (`generate_schedule`)

1. Detect interval granularity (`detect_interval_minutes`)
2. Calculate temperature-adjusted discharge hours
3. Split curve by date (today / tomorrow)
4. Calculate price ranges per day (`calculate_price_ranges`)
5. Find upcoming windows (`find_upcoming_windows`) → charge / discharge / adaptive
6. Apply sell-wait heuristic (defer discharge if better morning window exists)
7. Calculate dynamic sell-buffer SOC; add pre-charge if needed
8. Build `charge_schedule`: expand slots, apply solar-aware power reduction
9. Build `discharge_schedule`: rank-scale power, filter by SOC feasibility
10. Fill remaining API slots with adaptive windows
11. Add current-interval adaptive fallback if price is adaptive and no active period
12. Publish to battery-api via MQTT

---

## Passive Solar Logic

Triggered when `passive_solar.enabled = true` and PV output exceeds `entry_threshold` (W).

- Publishes a gap schedule (0W charge, 1-minute slot) so the inverter self-consumes solar.
- **Suppressed** when: a discharge window is active, or today has more than `negative_price_block_hours` of negative import prices.
- Exits when PV drops below `exit_threshold`.

---

## Negative Price Charging

When import prices are negative (grid pays to consume), the battery charges at maximum power regardless of the regular top-X scheduling.

- **Classification**: `_determine_price_range()` always returns `"load"` when `import_price < 0`, bypassing top-X range checks.
- **Window inclusion**: `find_upcoming_windows()` always adds negative-price slots to `charge_slots`, even if outside the `load_range`.
- **Slot priority**: In `generate_schedule()`, negative-price windows fill API charge slots first (pass 1), regular windows fill remaining slots (pass 2).
- **Power**: Always `max_charge_power` — no rank scaling.
- **Solar-aware**: Deliberately bypassed — charging at full speed is always better than leaving room for solar when prices are negative.
- **`window_type`**: `"negative_price_charge"`
- **Toggle**: `negative_price_charging.enabled` (default: `true`).

---

## Negative Price Handling

`_has_negative_price_block(curve, interval_minutes, min_hours)` returns `True` when the number of negative-price intervals × interval_minutes exceeds `min_hours × 60`.

Currently used to suppress Passive Solar when negative prices dominate the day. **If you add dedicated negative-price charging logic, document it here.**

---

## Adaptive Power Control (`monitor_loop`)

When `price_range == "adaptive"` and a discharge period is active:

1. Read `grid_power` sensor.
2. Compute `raw_target = current_power + grid_power`.
3. Round to nearest 100W, clamp to `[min_discharge_power, max_discharge_power]`.
4. Only apply if delta ≥ 100W (hysteresis).
5. Honour `adaptive_power_grace_seconds` after last adjustment.

---

## SOC Guardian Rules

| Condition | Action |
|-----------|--------|
| `soc >= max_soc` | Skip charge windows |
| `soc < min_soc` | Pause all discharge |
| `soc <= conservative_soc` during discharge | Switch to adaptive (not hard stop) |
| `soc <= conservative_soc`, price = adaptive, no active window | Trigger schedule regen to add adaptive fallback window (is_conservative=False for adaptive band) |
| `soc < sell_buffer_required_soc` | Pause discharge (sell-buffer protection) |

`sell_buffer_required_soc` is recalculated every `generate_schedule` call based on planned discharge hours before the next charge window.

**Conservative SOC and adaptive discharge:** `conservative_soc` blocks full-power scheduled discharge windows but does NOT block adaptive discharge (grid≈0W). `_should_regenerate_live_schedule` uses `is_conservative=False` when checking whether to regen for the adaptive price band, so SOC between `min_soc` and `conservative_soc` still triggers adaptive regen. `generate_schedule()` MUST also downgrade the current live interval from `discharge` to `adaptive` when SOC is already at/below `conservative_soc`, otherwise rolling schedule regeneration will keep republishing a schedule with no active adaptive slot.

---

## Entity List (`sensor.battery_manager_*`)

| Object ID | Description |
|-----------|-------------|
| `status` | High-level status message |
| `reasoning` | "Today's Energy Market" — current price story |
| `forecast` | Tomorrow's price story |
| `price_ranges` | Load / discharge / adaptive range boundaries |
| `current_action` | What the battery is doing right now |
| `charge_schedule` | Upcoming charge windows display |
| `discharge_schedule` | Upcoming discharge windows display |
| `schedule` | Combined charge+discharge table (part 1, ≤255 chars) |
| `schedule_part_2` | Combined schedule overflow (part 2) |
| `mode` | Effective operating mode |
| `effective_discharge_power` | Current discharge power in W |

---

## Configuration Sections

| Section | Key options |
|---------|-------------|
| `entities` | HA sensor entity IDs |
| `timing` | `update_interval`, `monitor_interval`, grace/cooldown |
| `power` | `max_charge_power`, `max_discharge_power`, `min_discharge_power`, `min_scaled_power` |
| `soc` | `min_soc`, `conservative_soc`, `target_eod_soc`, `max_soc`, `battery_capacity_kwh`, sell-buffer params |
| `heuristics` | `adaptive_price_threshold`, `top_x_charge_hours`, `top_x_discharge_hours`, `min_profit_threshold`, sell-wait params |
| `temperature_based_discharge` | thresholds list: `temp_max` → `discharge_hours` |
| `passive_solar` | `enabled`, `entry_threshold`, `exit_threshold`, `negative_price_block_hours` |
| `solar_aware_charging` | `enabled`, `forecast_safety_factor`, `min_charge_power` |
| `negative_price_charging` | `enabled` |
| `adaptive` | `enabled` |
| `ev_charger` | `enabled`, `charging_threshold`, `entity_id` |

---

## Mandatory Update Rules

After any change to `battery-manager/`:

| Changed | Update |
|---------|--------|
| New config option | `config.yaml` schema + defaults + `README.md` + this file (Configuration section) |
| New entity | `status_reporter.py` `ALL_ENTITIES` + `publish_all_entities()` + this file (Entity list) |
| New `window_type` | This file (window_type table) + `status_reporter.py` display logic |
| New price band or mode | This file (Price Range Semantics) + `_determine_price_range()` + entity label maps |
| New module | This file (Module Responsibilities table) |
| Logic change affecting schedule behavior | This file (relevant section) + `CHANGELOG.md` |
| User-facing behavior change | `README.md` + `CHANGELOG.md` |
