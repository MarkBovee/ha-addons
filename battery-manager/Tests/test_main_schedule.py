"""Targeted regression tests for schedule day-splitting helpers."""

import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.main import _should_wait_for_overnight, _split_curve_by_date


def _local_iso(local_date, hour: int) -> str:
    local_tz = datetime.now().astimezone().tzinfo
    local_dt = datetime(
        local_date.year,
        local_date.month,
        local_date.day,
        hour,
        0,
        tzinfo=local_tz,
    )
    return local_dt.astimezone(timezone.utc).isoformat()


def test_split_curve_by_date_uses_local_day_boundary():
    now = datetime(2026, 3, 4, 12, 0, tzinfo=timezone.utc)
    local_today = now.astimezone().date()
    local_tomorrow = local_today + timedelta(days=1)

    curve = [
        {"start": _local_iso(local_today, 10), "price": 0.20},
        {"start": _local_iso(local_tomorrow, 10), "price": 0.30},
    ]

    today_curve, tomorrow_curve = _split_curve_by_date(curve, now)

    assert len(today_curve) == 1
    assert len(tomorrow_curve) == 1
    assert today_curve[0]["price"] == 0.20
    assert tomorrow_curve[0]["price"] == 0.30


def test_should_wait_for_overnight_uses_local_hours():
    now = datetime(2026, 3, 4, 12, 0, tzinfo=timezone.utc)
    local_today = now.astimezone().date()
    local_tomorrow = local_today + timedelta(days=1)

    today_curve = [
        {"start": _local_iso(local_today, 20), "price": 0.40},
        {"start": _local_iso(local_today, 21), "price": 0.42},
    ]
    tomorrow_curve = [
        {"start": _local_iso(local_tomorrow, 1), "price": 0.20},
        {"start": _local_iso(local_tomorrow, 2), "price": 0.21},
    ]

    assert _should_wait_for_overnight(today_curve, tomorrow_curve, threshold=0.05) is True
