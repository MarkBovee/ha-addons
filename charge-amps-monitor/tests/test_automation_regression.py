from datetime import datetime, timezone
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.automation import AutomationConfig, ChargingAutomationCoordinator
from app.price_slot_analyzer import PriceSlot


class _Ha:
    pass


class _SchedulePort:
    def __init__(self):
        self.calls = []

    def upsert_schedule(self, **kwargs):
        self.calls.append(kwargs)
        return {"scheduleId": 42}

    def get_schedules(self, charge_point_id):
        return [{"scheduleId": 42}]


def _coordinator(port):
    return ChargingAutomationCoordinator(
        port,
        _Ha(),
        AutomationConfig(
            enabled=True,
            operation_mode="standalone",
            price_entity_id="sensor.prices",
            top_x_charge_count=2,
            price_threshold=0.25,
            max_current_per_phase=12,
            connector_id=1,
            timezone="Europe/Amsterdam",
        ),
    )


def test_schedule_periods_merge_and_keep_week_anchor():
    coordinator = _coordinator(_SchedulePort())
    week_start = datetime(2026, 9, 7, tzinfo=timezone.utc)
    slots = [
        PriceSlot(week_start, week_start.replace(hour=0, minute=15), 0.10, 1),
        PriceSlot(week_start.replace(hour=0, minute=15), week_start.replace(hour=0, minute=30), 0.11, 2),
        PriceSlot(week_start.replace(hour=1), week_start.replace(hour=1, minute=15), 0.12, 3),
    ]

    periods = coordinator._slots_to_schedule_periods(slots, week_start)

    assert periods == [{"from": 0, "to": 1800}, {"from": 3600, "to": 4500}]


def test_standalone_schedule_push_requires_readback_and_preserves_payload():
    port = _SchedulePort()
    coordinator = _coordinator(port)
    now = datetime.now(coordinator._tz)
    coordinator._last_schedule = type("Schedule", (), {
        "today_slots": [PriceSlot(now, now.replace(minute=(now.minute + 15) % 60), 0.10, 1)],
        "tomorrow_slots": [],
    })()

    assert coordinator.push_schedule_to_charger("charger-1") is True
    assert port.calls[0]["charge_point_id"] == "charger-1"
    assert port.calls[0]["connector_id"] == 1
    assert port.calls[0]["max_current"] == 12.0
    assert port.calls[0]["timezone_name"] == "Europe/Amsterdam"
