"""Synthetic 15-minute price curves modelled on 2026-10-07/08 (Europe/Amsterdam, CEST).

The numbers are reconstructed from the incident description (HA history was not
available): midday import ~0.31, evening export 0.465-0.47 at 17:45-19:15, 0.42
falling to 0.38 until 22:00, night 0.334/0.315, tomorrow 08:00 = 0.401 and
19:00 = 0.422. The midday export price (the forgone price of PV energy) is an
assumption (0.20).
"""

from datetime import datetime, timedelta, timezone
from typing import Dict, List, Tuple

CEST = timezone(timedelta(hours=2))

# (from "HH:MM", price) breakpoints, each valid until the next breakpoint.
IMPORT_TODAY: List[Tuple[str, float]] = [
    ("00:00", 0.330), ("06:00", 0.345), ("07:00", 0.370), ("09:00", 0.350),
    ("10:00", 0.330), ("11:15", 0.310), ("16:00", 0.370), ("17:00", 0.400),
    ("17:30", 0.440), ("17:45", 0.470), ("18:00", 0.468), ("18:15", 0.466),
    ("18:30", 0.470), ("18:45", 0.468), ("19:00", 0.466), ("19:15", 0.420),
    ("20:00", 0.405), ("21:00", 0.385), ("21:45", 0.334), ("22:00", 0.340),
    ("22:45", 0.315),
]
EXPORT_TODAY: List[Tuple[str, float]] = [
    ("00:00", 0.320), ("06:00", 0.335), ("07:00", 0.360), ("09:00", 0.340),
    ("10:00", 0.300), ("11:15", 0.200), ("16:00", 0.360), ("17:00", 0.395),
    ("17:30", 0.435), ("17:45", 0.470), ("18:00", 0.463), ("18:15", 0.462),
    ("18:30", 0.470), ("18:45", 0.466), ("19:00", 0.465), ("19:15", 0.420),
    ("20:00", 0.400), ("21:00", 0.380), ("21:45", 0.325), ("22:00", 0.330),
    ("22:45", 0.310),
]
IMPORT_TOMORROW: List[Tuple[str, float]] = [
    ("00:00", 0.310), ("06:00", 0.360), ("07:30", 0.400), ("08:00", 0.401),
    ("08:30", 0.370), ("10:00", 0.330), ("11:30", 0.300), ("16:00", 0.370),
    ("18:30", 0.410), ("19:00", 0.422), ("20:00", 0.400), ("22:00", 0.340),
]
EXPORT_TOMORROW: List[Tuple[str, float]] = [
    (hhmm, round(price - 0.005, 3)) for hhmm, price in IMPORT_TOMORROW
]


def at(day: int, hhmm: str) -> datetime:
    """Return a CEST datetime on 2026-10-<day>."""
    hour, minute = (int(part) for part in hhmm.split(":"))
    return datetime(2026, 10, day, hour, minute, tzinfo=CEST)


def _build(day: int, points: List[Tuple[str, float]]) -> List[Dict[str, object]]:
    entries: List[Dict[str, object]] = []
    start = at(day, "00:00")
    for index in range(96):
        slot_start = start + timedelta(minutes=15 * index)
        price = points[0][1]
        for hhmm, value in points:
            if slot_start >= at(day, hhmm):
                price = value
        entries.append({
            "start": slot_start.isoformat(),
            "end": (slot_start + timedelta(minutes=15)).isoformat(),
            "price": price,
        })
    return entries


def import_curve(include_tomorrow: bool = True) -> List[Dict[str, object]]:
    curve = _build(7, IMPORT_TODAY)
    return curve + _build(8, IMPORT_TOMORROW) if include_tomorrow else curve


def export_curve(include_tomorrow: bool = True) -> List[Dict[str, object]]:
    curve = _build(7, EXPORT_TODAY)
    return curve + _build(8, EXPORT_TOMORROW) if include_tomorrow else curve
