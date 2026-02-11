"""MQTT Discovery entity management for Battery Manager.

Uses the shared MqttDiscovery class to create and update entities in Home Assistant
with proper unique_id, device grouping, and JSON attributes support.

Entity prefix: bm_ (battery manager)
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from dateutil.parser import isoparse

from shared.ha_mqtt_discovery import MqttDiscovery, EntityConfig

logger = logging.getLogger(__name__)

# --- Entity object_id constants (used as keys into MqttDiscovery) ---
ENTITY_STATUS = "status"
ENTITY_REASONING = "reasoning"
ENTITY_FORECAST = "forecast"
ENTITY_PRICE_RANGES = "price_ranges"
ENTITY_CURRENT_ACTION = "current_action"
ENTITY_CHARGE_SCHEDULE = "charge_schedule"
ENTITY_DISCHARGE_SCHEDULE = "discharge_schedule"
ENTITY_SCHEDULE = "schedule"
ENTITY_MODE = "mode"

ALL_ENTITIES = [
    ENTITY_STATUS,
    ENTITY_REASONING,
    ENTITY_FORECAST,
    ENTITY_PRICE_RANGES,
    ENTITY_CURRENT_ACTION,
    ENTITY_CHARGE_SCHEDULE,
    ENTITY_DISCHARGE_SCHEDULE,
    ENTITY_SCHEDULE,
    ENTITY_MODE,
]


def publish_all_entities(mqtt: MqttDiscovery) -> None:
    """Register all Battery Manager entities via MQTT Discovery."""
    configs = [
        EntityConfig(
            object_id=ENTITY_STATUS,
            name="Battery Manager Status",
            state="idle",
            icon="mdi:battery-sync",
        ),
        EntityConfig(
            object_id=ENTITY_REASONING,
            name="Battery Manager Reasoning",
            state="unknown",
            icon="mdi:head-lightbulb",
        ),
        EntityConfig(
            object_id=ENTITY_FORECAST,
            name="Battery Manager Forecast",
            state="unknown",
            icon="mdi:crystal-ball",
        ),
        EntityConfig(
            object_id=ENTITY_PRICE_RANGES,
            name="Battery Manager Price Ranges",
            state="unknown",
            icon="mdi:chart-bar",
        ),
        EntityConfig(
            object_id=ENTITY_CURRENT_ACTION,
            name="Battery Manager Current Action",
            state="idle",
            icon="mdi:play-circle",
        ),
        EntityConfig(
            object_id=ENTITY_CHARGE_SCHEDULE,
            name="Battery Manager Charge Schedule",
            state="No charge planned",
            icon="mdi:battery-charging",
        ),
        EntityConfig(
            object_id=ENTITY_DISCHARGE_SCHEDULE,
            name="Battery Manager Discharge Schedule",
            state="No discharge planned",
            icon="mdi:battery-arrow-down",
        ),
        EntityConfig(
            object_id=ENTITY_SCHEDULE,
            name="Battery Manager Schedule",
            state="No schedule",
            icon="mdi:calendar-clock",
        ),
        EntityConfig(
            object_id=ENTITY_MODE,
            name="Battery Manager Mode",
            state="unknown",
            icon="mdi:cog",
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

    for period in periods:
        start_str = period.get("start")
        duration = period.get("duration", 0)
        if not start_str:
            continue
        try:
            start_dt = isoparse(start_str)
            if start_dt.tzinfo is None:
                start_dt = start_dt.replace(tzinfo=timezone.utc)
            end_dt = start_dt + timedelta(minutes=int(duration))
        except Exception:
            continue

        now_aware = now if now.tzinfo else now.replace(tzinfo=timezone.utc)
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

    for period_type in ["charge", "discharge"]:
        icon = "⚡" if period_type == "charge" else "📤"
        label = "Charge" if period_type == "charge" else "Discharge"
        for period in schedule.get(period_type, []):
            start_str = period.get("start")
            duration = period.get("duration", 0)
            power = period.get("power", 0)
            if not start_str:
                continue
            try:
                start_dt = isoparse(start_str)
                if start_dt.tzinfo is None:
                    start_dt = start_dt.replace(tzinfo=timezone.utc)
                end_dt = start_dt + timedelta(minutes=int(duration))
            except Exception:
                continue

            now_aware = now if now.tzinfo else now.replace(tzinfo=timezone.utc)
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
