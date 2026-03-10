"""MQTT Discovery entity management for Battery Manager.

Uses the shared MqttDiscovery class to create and update entities in Home Assistant
with proper unique_id, device grouping, and JSON attributes support.

Entity naming: sensor.battery_manager_{object_id}
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Set

from dateutil.parser import isoparse

from shared.ha_mqtt_discovery import MqttDiscovery, EntityConfig
from .price_analyzer import PriceRange

logger = logging.getLogger(__name__)

# --- Entity object_id constants (used as keys into MqttDiscovery) ---
# Entity IDs without prefix to match existing HA entities (sensor.battery_manager_*)
ENTITY_STATUS = "status"
ENTITY_REASONING = "reasoning"
ENTITY_FORECAST = "forecast"
ENTITY_PRICE_RANGES = "price_ranges"
ENTITY_CURRENT_ACTION = "current_action"
ENTITY_CHARGE_SCHEDULE = "charge_schedule"
ENTITY_DISCHARGE_SCHEDULE = "discharge_schedule"
ENTITY_SCHEDULE = "schedule"
ENTITY_SCHEDULE_2 = "schedule_part_2"
ENTITY_MODE = "mode"
ENTITY_EFFECTIVE_DISCHARGE_POWER = "effective_discharge_power"

ALL_ENTITIES = [
    ENTITY_STATUS,
    ENTITY_REASONING,
    ENTITY_FORECAST,
    ENTITY_PRICE_RANGES,
    ENTITY_CURRENT_ACTION,
    ENTITY_CHARGE_SCHEDULE,
    ENTITY_DISCHARGE_SCHEDULE,
    ENTITY_SCHEDULE,
    ENTITY_SCHEDULE_2,
    ENTITY_MODE,
    ENTITY_EFFECTIVE_DISCHARGE_POWER,
]


def publish_all_entities(mqtt: MqttDiscovery) -> None:
    """Register all Battery Manager entities via MQTT Discovery.

    Entity names are short (device 'Battery Manager' provides context).
    HA entity IDs: sensor.battery_manager_status, sensor.battery_manager_reasoning, etc.
    """
    configs = [
        EntityConfig(
            object_id=ENTITY_STATUS,
            name="Status",
            state="idle",
            icon="mdi:battery-sync",
        ),
        EntityConfig(
            object_id=ENTITY_REASONING,
            name="Reasoning",
            state="unknown",
            icon="mdi:head-lightbulb",
        ),
        EntityConfig(
            object_id=ENTITY_FORECAST,
            name="Forecast",
            state="unknown",
            icon="mdi:crystal-ball",
        ),
        EntityConfig(
            object_id=ENTITY_PRICE_RANGES,
            name="Price Ranges",
            state="unknown",
            icon="mdi:chart-bar",
        ),
        EntityConfig(
            object_id=ENTITY_CURRENT_ACTION,
            name="Current Action",
            state="idle",
            icon="mdi:play-circle",
        ),
        EntityConfig(
            object_id=ENTITY_CHARGE_SCHEDULE,
            name="Charge Schedule",
            state="No charge planned",
            icon="mdi:battery-charging",
        ),
        EntityConfig(
            object_id=ENTITY_DISCHARGE_SCHEDULE,
            name="Discharge Schedule",
            state="No discharge planned",
            icon="mdi:battery-arrow-down",
        ),
        EntityConfig(
            object_id=ENTITY_SCHEDULE,
            name="Schedule",
            state="No schedule",
            icon="mdi:calendar-clock",
        ),
        EntityConfig(
            object_id=ENTITY_SCHEDULE_2,
            name="Schedule (Part 2)",
            state=" ",
            icon="mdi:calendar-clock",
        ),
        EntityConfig(
            object_id=ENTITY_MODE,
            name="Mode",
            state="unknown",
            icon="mdi:cog",
        ),
        EntityConfig(
            object_id=ENTITY_EFFECTIVE_DISCHARGE_POWER,
            name="Effective Discharge Power",
            state="unknown",
            unit_of_measurement="W",
            device_class="power",
            state_class="measurement",
            icon="mdi:flash",
        ),
    ]
    for cfg in configs:
        mqtt.publish_sensor(cfg)
    logger.info("Published %d MQTT Discovery entities", len(configs))


def update_entity(
    mqtt: Optional[MqttDiscovery],
    entity_id: str,
    state: str,
    attributes: Optional[Dict[str, Any]] = None,
    dry_run: bool = False,
) -> None:
    """Update an entity state (and optional attributes)."""
    if dry_run:
        logger.info(
            "📝 [Dry-Run] %s = %s %s",
            entity_id,
            state,
            f"| attrs={attributes}" if attributes else "",
        )
        return

    if mqtt is None:
        return

    mqtt.update_state("sensor", entity_id, state, attributes)


def _to_aware(dt: datetime) -> datetime:
    """Ensure datetime has timezone information for consistent comparisons."""
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _parse_period_bounds(period: Dict[str, Any]) -> Optional[tuple[datetime, datetime]]:
    """Parse period start/duration into aware start/end datetimes."""
    start_str = period.get("start")
    duration = period.get("duration", 0)
    if not start_str:
        return None
    try:
        start_dt = isoparse(start_str)
        start_dt = _to_aware(start_dt)
        end_dt = start_dt + timedelta(minutes=int(duration))
    except Exception:
        return None
    return start_dt, end_dt


# ---------------------------------------------------------------------------
# Status message builders (matching legacy NetDaemon app patterns)
# ---------------------------------------------------------------------------

def get_temperature_icon(temperature: Optional[float]) -> str:
    """Get weather emoji based on temperature thresholds."""
    if temperature is None:
        return ""
    if temperature < 0:
        return "❄️"
    if temperature < 8:
        return "🥶"
    if temperature < 16:
        return "🌥️"
    if temperature < 20:
        return "🌤️"
    return "☀️"


def build_status_message(
    price_range: str,
    active_charge: bool,
    active_discharge: bool,
    charge_power: Optional[int],
    discharge_power: Optional[int],
    temperature: Optional[float],
    paused: bool = False,
    reduced: bool = False,
    pause_reason: str = "",
) -> str:
    """Build a concise dashboard status message like the old NetDaemon app.

    Examples:
        "Charging Active (8000W) ☀️ 22°C"
        "Discharging Active (6000W) 🌤️ 18°C"
        "Idle | Adaptive 🌥️ 14°C"
        "Paused | EV Charging"
    """
    temp_str = ""
    if temperature is not None:
        icon = get_temperature_icon(temperature)
        temp_str = f" {icon} {temperature:.0f}°C"

    if paused:
        return f"Paused | {pause_reason}{temp_str}"
    if reduced:
        return f"Reduced | {pause_reason}{temp_str}"

    if active_charge:
        power_str = f" ({charge_power}W)" if charge_power else ""
        return f"Charging Active{power_str}{temp_str}"
    if active_discharge:
        power_str = f" ({discharge_power}W)" if discharge_power else ""
        return f"Discharging Active{power_str}{temp_str}"

    return f"Idle | {price_range.capitalize()}{temp_str}"


def build_next_event_summary(
    schedule: Dict[str, Any],
    now: datetime,
    temperature: Optional[float] = None,
) -> str:
    """Build a summary of the next upcoming event in the schedule."""
    upcoming: List[Dict[str, Any]] = []

    for period_type in ["charge", "discharge"]:
        for period in schedule.get(period_type, []):
            start_str = period.get("start")
            if not start_str:
                continue
            try:
                start_dt = isoparse(start_str)
                if start_dt.tzinfo is None:
                    start_dt = start_dt.replace(tzinfo=timezone.utc)
            except Exception:
                continue
            if start_dt > now:
                upcoming.append({
                    "type": period_type,
                    "start": start_dt,
                    "power": period.get("power", 0),
                })

    upcoming.sort(key=lambda x: x["start"])

    temp_str = ""
    if temperature is not None:
        icon = get_temperature_icon(temperature)
        temp_str = f" {icon} {temperature:.0f}°C"

    if not upcoming:
        return f"No upcoming events{temp_str}"

    if len(upcoming) == 1:
        ev = upcoming[0]
        label = "Charge" if ev["type"] == "charge" else "Discharge"
        return f"Next: {label} {ev['power']}W at {ev['start'].strftime('%H:%M')}{temp_str}"

    parts = []
    for ev in upcoming[:2]:
        label = "Charge" if ev["type"] == "charge" else "Discharge"
        parts.append(f"{label} {ev['power']}W at {ev['start'].strftime('%H:%M')}")
    return f"Upcoming: {', '.join(parts)}{temp_str}"


def build_schedule_display(
    schedule: Dict[str, Any],
    period_type: str,
    now: datetime,
) -> str:
    """Build charge or discharge schedule display string.

    Returns "Active: 8000W" or "Next: 8000W at 02:00" or "No charge planned"
    """
    periods = schedule.get(period_type, [])
    if not periods:
        return f"No {period_type} planned"

    active = None
    next_period = None

    now_aware = _to_aware(now)
    for period in periods:
        bounds = _parse_period_bounds(period)
        if bounds is None:
            continue
        start_dt, end_dt = bounds

        if start_dt <= now_aware < end_dt:
            active = period
            break
        elif start_dt > now_aware and next_period is None:
            next_period = (period, start_dt)

    if active:
        return f"Active: {active.get('power', 0)}W"
    if next_period:
        p, sdt = next_period
        return f"Next: {p.get('power', 0)}W at {sdt.strftime('%H:%M')}"
    return f"No {period_type} planned"


def build_schedule_markdown(schedule: Dict[str, Any], now: datetime) -> str:
    """Build a compact markdown table of the schedule.

    Format matches legacy NetDaemon app:
        |Time|Type|Power|
        |---|---|---|
        |🔴 02:00-02:15|⚡ Charge|8000W|
        |✅ 17:00-17:15|📤 Discharge|6000W|
        |⏰ 18:00-18:15|📤 Discharge|4000W|
    """
    rows: List[Dict[str, Any]] = []

    now_aware = _to_aware(now)
    for period_type in ["charge", "discharge"]:
        icon = "⚡" if period_type == "charge" else "📤"
        label = "Charge" if period_type == "charge" else "Discharge"
        for period in schedule.get(period_type, []):
            power = period.get("power", 0)
            bounds = _parse_period_bounds(period)
            if bounds is None:
                continue
            start_dt, end_dt = bounds

            if end_dt <= now_aware:
                status = "✅"
            elif start_dt <= now_aware < end_dt:
                status = "🔴"
            else:
                status = "⏰"

            rows.append({
                "start_dt": start_dt,
                "time": f"{status} {start_dt.strftime('%H:%M')}-{end_dt.strftime('%H:%M')}",
                "type": f"{icon} {label}",
                "power": f"{power}W",
            })

    rows.sort(key=lambda r: r["start_dt"])

    if not rows:
        return "No schedule"

    lines = ["|Time|Type|Power|", "|---|---|---|"]
    for row in rows:
        lines.append(f"|{row['time']}|{row['type']}|{row['power']}|")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Rich text builders (matching legacy NetDaemon quality)
# ---------------------------------------------------------------------------

_RANGE_ICONS = {
    "load": "🔋 Charging",
    "discharge": "💰 Profit",
    "adaptive": "⚖️ Adaptive",
    "passive": "💤 Passive",
}


def _trading_quality(spread: float) -> str:
    """Rate the trading spread quality."""
    if spread >= 0.10:
        return "🚀 Excellent"
    if spread >= 0.05:
        return "💰 Good"
    if spread >= 0.02:
        return "📊 Moderate"
    return "📉 Limited"


def build_today_story(
    price_range: str,
    import_price: float,
    export_price: float,
    load_range: Optional[PriceRange],
    discharge_range: Optional[PriceRange],
    adaptive_range: Optional[PriceRange],
    adaptive_price_threshold: Optional[float] = None,
    now: Optional[datetime] = None,
) -> str:
    """Build rich 'Today's Energy Market' text for the reasoning entity."""
    if now is None:
        now = datetime.now(timezone.utc)

    lines = ["📊 Today's Energy Market"]

    if load_range:
        lines.append(f"🔋 Charging: €{load_range.min_price:.3f} – €{load_range.max_price:.3f}")
    if adaptive_range and adaptive_price_threshold is not None:
        # Split adaptive range into passive (below threshold) and balancing (at/above)
        if adaptive_price_threshold > adaptive_range.min_price:
            lines.append(f"💤 Passive: €{adaptive_range.min_price:.3f} – €{adaptive_price_threshold:.3f}")
        if adaptive_price_threshold < adaptive_range.max_price:
            balancing_min = max(adaptive_range.min_price, adaptive_price_threshold)
            lines.append(f"⚖️ Balancing: €{balancing_min:.3f} – €{adaptive_range.max_price:.3f}")
    elif adaptive_range:
        lines.append(f"⚖️ Balancing: €{adaptive_range.min_price:.3f} – €{adaptive_range.max_price:.3f}")
    elif adaptive_price_threshold is not None:
        lines.append(f"💤 Passive below €{adaptive_price_threshold:.3f}")
    if discharge_range:
        lines.append(f"💰 Selling: €{discharge_range.min_price:.3f} – €{discharge_range.max_price:.3f}")

    if load_range and discharge_range:
        min_profit_kwh = discharge_range.min_price - load_range.max_price
        max_profit_kwh = discharge_range.max_price - load_range.min_price
        lines.append(f"💵 Profit: €{min_profit_kwh:.3f}–€{max_profit_kwh:.3f}/kWh — {_trading_quality(min_profit_kwh)}")

    range_label = _RANGE_ICONS.get(price_range, price_range.capitalize())
    # Display time in local timezone
    now_local = now.astimezone()
    lines.append(f"📍 Now ({now_local.strftime('%H:%M')}): €{import_price:.3f}/kWh — {range_label}")

    return "\n".join(lines)


def build_tomorrow_story(
    tomorrow_load: Optional[PriceRange],
    tomorrow_discharge: Optional[PriceRange],
    tomorrow_adaptive: Optional[PriceRange],
    tomorrow_curve: Optional[List[Dict[str, Any]]] = None,
    adaptive_price_threshold: Optional[float] = None,
) -> str:
    """Build rich 'Tomorrow's Forecast' text for the forecast entity."""
    if not tomorrow_load and not tomorrow_discharge:
        return "🔮 Tomorrow: Prices not yet available (usually after 14:00)"

    lines = ["🔮 Tomorrow's Forecast"]

    if tomorrow_load:
        lines.append(f"🔋 Charging: €{tomorrow_load.min_price:.3f} – €{tomorrow_load.max_price:.3f}")
    if tomorrow_adaptive and adaptive_price_threshold is not None:
        if adaptive_price_threshold > tomorrow_adaptive.min_price:
            lines.append(f"💤 Passive: €{tomorrow_adaptive.min_price:.3f} – €{adaptive_price_threshold:.3f}")
        if adaptive_price_threshold < tomorrow_adaptive.max_price:
            balancing_min = max(tomorrow_adaptive.min_price, adaptive_price_threshold)
            lines.append(f"⚖️ Balancing: €{balancing_min:.3f} – €{tomorrow_adaptive.max_price:.3f}")
    elif tomorrow_adaptive:
        lines.append(f"⚖️ Balancing: €{tomorrow_adaptive.min_price:.3f} – €{tomorrow_adaptive.max_price:.3f}")
    if tomorrow_discharge:
        lines.append(f"💰 Selling: €{tomorrow_discharge.min_price:.3f} – €{tomorrow_discharge.max_price:.3f}")

    if tomorrow_load and tomorrow_discharge:
        min_profit_kwh = tomorrow_discharge.min_price - tomorrow_load.max_price
        max_profit_kwh = tomorrow_discharge.max_price - tomorrow_load.min_price
        lines.append(f"💵 Profit: €{min_profit_kwh:.3f}–€{max_profit_kwh:.3f}/kWh — {_trading_quality(min_profit_kwh)}")

    # First charge window from curve
    if tomorrow_curve and tomorrow_load:
        for entry in sorted(tomorrow_curve, key=lambda e: e.get("start", "")):
            price = entry.get("price")
            if price is None:
                continue
            if tomorrow_load.min_price <= float(price) <= tomorrow_load.max_price:
                try:
                    start_dt = isoparse(entry["start"])
                    lines.append(f"⏰ First charge window: {start_dt.astimezone().strftime('%H:%M')}")
                except Exception:
                    pass
                break

    return "\n".join(lines)


def build_price_ranges_display(
    load_range: Optional[PriceRange],
    discharge_range: Optional[PriceRange],
    adaptive_range: Optional[PriceRange],
    adaptive_price_threshold: Optional[float] = None,
) -> str:
    """Build readable price ranges state text for the price_ranges entity."""
    parts = []
    if load_range:
        parts.append(f"Load: €{load_range.min_price:.3f}–{load_range.max_price:.3f}")
    if adaptive_range and adaptive_price_threshold is not None:
        if adaptive_price_threshold > adaptive_range.min_price:
            parts.append(f"Passive: €{adaptive_range.min_price:.3f}–{adaptive_price_threshold:.3f}")
        if adaptive_price_threshold < adaptive_range.max_price:
            balancing_min = max(adaptive_range.min_price, adaptive_price_threshold)
            parts.append(f"Adaptive: €{balancing_min:.3f}–{adaptive_range.max_price:.3f}")
    elif adaptive_range:
        parts.append(f"Adaptive: €{adaptive_range.min_price:.3f}–{adaptive_range.max_price:.3f}")
    elif adaptive_price_threshold is not None:
        parts.append(f"Passive: <€{adaptive_price_threshold:.3f}")
    if discharge_range:
        parts.append(f"Discharge: €{discharge_range.min_price:.3f}–{discharge_range.max_price:.3f}")
    return " | ".join(parts) if parts else "No price data"


def find_upcoming_windows(
    import_curve: List[Dict[str, Any]],
    export_curve: Optional[List[Dict[str, Any]]],
    load_range: Optional[PriceRange],
    discharge_range: Optional[PriceRange],
    adaptive_price_threshold: Optional[float],
    now: datetime,
    tomorrow_load_range: Optional[PriceRange] = None,
    tomorrow_discharge_range: Optional[PriceRange] = None,
    discharge_slot_starts: Optional[Set[str]] = None,
    tomorrow_discharge_slot_starts: Optional[Set[str]] = None,
    adaptive_enabled: bool = True,
) -> Dict[str, List[Dict[str, Any]]]:
    """Scan full price curves and find all upcoming charge/discharge/adaptive windows.

    Uses per-day ranges when tomorrow ranges are provided: today's slots are
    classified with today's ranges, tomorrow's slots with tomorrow's ranges.

    Returns dict with 'charge', 'discharge', and 'adaptive' lists of grouped windows:
    [{"start": datetime, "end": datetime, "avg_price": float}, ...]

    Adaptive windows are slots where the price is above the adaptive_price_threshold
    but not in the load or discharge range — the battery should discharge adaptively
    (targeting 0W grid export) during these periods.
    """
    now_aware = now if now.tzinfo else now.replace(tzinfo=timezone.utc)
    tomorrow_start = (now_aware + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)

    # Build export price lookup by start timestamp
    export_by_start: Dict[str, float] = {}
    if export_curve:
        for entry in export_curve:
            s = entry.get("start")
            if s and entry.get("price") is not None:
                export_by_start[s] = float(entry["price"])

    charge_slots: List[Dict[str, Any]] = []
    discharge_slots: List[Dict[str, Any]] = []
    adaptive_slots: List[Dict[str, Any]] = []

    # Include all of today's periods (past shown as completed) but exclude yesterday
    today_start = now_aware.replace(hour=0, minute=0, second=0, microsecond=0)

    for entry in import_curve:
        start_str = entry.get("start")
        end_str = entry.get("end")
        price = entry.get("price")
        if not start_str or price is None:
            continue
        try:
            start_dt = isoparse(start_str)
            if start_dt.tzinfo is None:
                start_dt = start_dt.replace(tzinfo=timezone.utc)
            if end_str:
                end_dt = isoparse(end_str)
                if end_dt.tzinfo is None:
                    end_dt = end_dt.replace(tzinfo=timezone.utc)
            else:
                end_dt = start_dt + timedelta(hours=1)
        except Exception:
            continue

        # Skip periods that ended before today
        if end_dt <= today_start:
            continue

        import_price = float(price)
        export_price = export_by_start.get(start_str, import_price)

        # Use per-day ranges when available
        is_tomorrow = start_dt >= tomorrow_start
        effective_load = (tomorrow_load_range if is_tomorrow and tomorrow_load_range else load_range)
        effective_discharge = (tomorrow_discharge_range if is_tomorrow and tomorrow_discharge_range else discharge_range)
        effective_discharge_starts = (
            tomorrow_discharge_slot_starts
            if is_tomorrow and tomorrow_discharge_slot_starts is not None
            else discharge_slot_starts
        )

        if effective_load and effective_load.min_price <= import_price <= effective_load.max_price:
            charge_slots.append({"start_dt": start_dt, "end_dt": end_dt, "price": import_price})
        elif effective_discharge_starts is not None:
            if start_str in effective_discharge_starts:
                discharge_slots.append({"start_dt": start_dt, "end_dt": end_dt, "price": export_price})
        elif effective_discharge and effective_discharge.min_price <= export_price <= effective_discharge.max_price:
            discharge_slots.append({"start_dt": start_dt, "end_dt": end_dt, "price": export_price})
        elif (
            adaptive_enabled
            and adaptive_price_threshold is not None
            and import_price >= adaptive_price_threshold
        ):
            # Above passive threshold but not in load/discharge — adaptive discharge
            adaptive_slots.append({"start_dt": start_dt, "end_dt": end_dt, "price": import_price})

    return {
        "charge": _group_consecutive_slots(charge_slots),
        "discharge": _group_consecutive_slots(discharge_slots),
        "adaptive": _group_consecutive_slots(adaptive_slots),
    }


def _group_consecutive_slots(
    slots: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Group consecutive time slots into windows with averaged price."""
    if not slots:
        return []
    slots.sort(key=lambda s: s["start_dt"])
    windows: List[Dict[str, Any]] = []
    cur = {
        "start": slots[0]["start_dt"],
        "end": slots[0]["end_dt"],
        "prices": [slots[0]["price"]],
        "slots": [{
            "start": slots[0]["start_dt"],
            "end": slots[0]["end_dt"],
            "price": slots[0]["price"],
        }],
    }
    for slot in slots[1:]:
        if slot["start_dt"] <= cur["end"]:
            cur["end"] = slot["end_dt"]
            cur["prices"].append(slot["price"])
            cur["slots"].append({
                "start": slot["start_dt"],
                "end": slot["end_dt"],
                "price": slot["price"],
            })
        else:
            windows.append({
                "start": cur["start"],
                "end": cur["end"],
                "avg_price": sum(cur["prices"]) / len(cur["prices"]),
                "slots": list(cur["slots"]),
            })
            cur = {
                "start": slot["start_dt"],
                "end": slot["end_dt"],
                "prices": [slot["price"]],
                "slots": [{
                    "start": slot["start_dt"],
                    "end": slot["end_dt"],
                    "price": slot["price"],
                }],
            }
    windows.append({
        "start": cur["start"],
        "end": cur["end"],
        "avg_price": sum(cur["prices"]) / len(cur["prices"]),
        "slots": list(cur["slots"]),
    })
    return windows


def _serialize_windows(windows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Convert window datetimes to ISO strings for JSON attributes."""
    return [
        {
            "start": w["start"].isoformat(),
            "end": w["end"].isoformat(),
            "avg_price": round(w["avg_price"], 4),
        }
        for w in windows
    ]


def build_windows_display(
    windows: List[Dict[str, Any]],
    window_type: str,
    power: Optional[int],
    now: datetime,
    no_range_reason: Optional[str] = None,
) -> str:
    """Build readable display for charge or discharge windows.

    Examples:
        "🔴 02:00–04:00 8000W (€0.231)"
        "⚡ 02:00–04:00 8000W (€0.231) | ⚡ 22:00–23:00 8000W (€0.234)"
    """
    if not windows:
        if no_range_reason:
            return no_range_reason
        label = "charge" if window_type == "charge" else "discharge"
        return f"No {label} windows today"

    now_aware = _to_aware(now)
    tomorrow_start = (now_aware + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    icon = "⚡" if window_type == "charge" else "💰"
    has_tomorrow = any(w["start"] >= tomorrow_start for w in windows)

    parts = []
    shown_tomorrow_header = False
    for w in windows:
        start = w["start"]
        end = w["end"]
        avg_price = w["avg_price"]
        window_power = w.get("power", power)

        if has_tomorrow and not shown_tomorrow_header and start >= tomorrow_start:
            parts.append("— Tomorrow —")
            shown_tomorrow_header = True

        if start <= now_aware < end:
            status = "🔴"
        elif end <= now_aware:
            status = "✅"
        else:
            status = icon

        parts.append(
            f"{status} {start.astimezone().strftime('%H:%M')}–{end.astimezone().strftime('%H:%M')} {window_power}W (€{avg_price:.3f})"
        )

    return "\n".join(parts)


def build_combined_schedule_display(
    windows: Dict[str, List[Dict[str, Any]]],
    charge_power: int,
    discharge_power: int,
    now: datetime,
    no_discharge_reason: Optional[str] = None,
    adaptive_power: Optional[int] = None,
) -> str:
    """Build combined schedule table with all charge/discharge windows.

    Format:
        |Time|Type|Power|Price|
        |---|---|---|---|
        |⚡ 02:00–04:00|Charge|8000W|€0.231|
        |💰 17:00–18:00|Discharge|6000W|€0.293|
    """
    now_aware = _to_aware(now)
    rows: List[Dict[str, Any]] = []

    for w in windows.get("charge", []):
        rows.append({
            "start": w["start"],
            "end": w["end"],
            "type": "charge",
            "power": w.get("power", charge_power),
            "price": w["avg_price"],
        })
    for w in windows.get("discharge", []):
        rows.append({
            "start": w["start"],
            "end": w["end"],
            "type": "discharge",
            "power": w.get("power", discharge_power),
            "price": w["avg_price"],
        })
    for w in windows.get("adaptive", []):
        rows.append({
            "start": w["start"],
            "end": w["end"],
            "type": "adaptive",
            "power": w.get("power", discharge_power if adaptive_power is None else adaptive_power),
            "price": w["avg_price"],
        })

    rows.sort(key=lambda r: r["start"])

    if not rows:
        parts = []
        if no_discharge_reason:
            parts.append(no_discharge_reason)
        parts.append("No scheduled windows today")
        return "\n".join(parts)

    lines = ["|Time|Type|Power|Price|", "|---|---|---|---|"]
    tomorrow_start = (now_aware + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    has_tomorrow = any(r["start"] >= tomorrow_start for r in rows)
    shown_tomorrow_header = False

    for row in rows:
        start = row["start"]
        end = row["end"]

        if has_tomorrow and not shown_tomorrow_header and start >= tomorrow_start:
            lines.append("|**Tomorrow**|||")
            shown_tomorrow_header = True

        if start <= now_aware < end:
            status = "🔴"
        elif end <= now_aware:
            status = "✅"
        else:
            status = "⏰"

        if row["type"] == "charge":
            icon, label = "⚡", "Charge"
        elif row["type"] == "discharge":
            icon, label = "💰", "Discharge"
        else:
            icon, label = "⚖️", "Adaptive"

        lines.append(
            f"|{status} {start.astimezone().strftime('%H:%M')}–{end.astimezone().strftime('%H:%M')}|{icon} {label}|{row['power']}W|€{row['price']:.3f}|"
        )
    return "\n".join(lines)
