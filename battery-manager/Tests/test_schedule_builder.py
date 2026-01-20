import logging
import pytest

from app.schedule_builder import build_charge_schedule, build_discharge_schedule, merge_schedules

logger = logging.getLogger("battery-manager-tests")


def test_build_charge_schedule():
    logger.info("schedule_builder: builds charge schedule entries")
    periods = [{"start": "01:00"}, {"start": "02:00", "duration": 30}]
    schedule = build_charge_schedule(periods, power=8000, duration_minutes=60)

    assert schedule == [
        {"start": "01:00", "power": 8000, "duration": 60},
        {"start": "02:00", "power": 8000, "duration": 30},
    ]


def test_build_discharge_schedule():
    logger.info("schedule_builder: builds discharge schedule entries")
    periods = [{"start": "18:00"}, {"start": "19:00"}]
    schedule = build_discharge_schedule(periods, power_ranks=[8000, 4000], duration_minutes=60)

    assert schedule == [
        {"start": "18:00", "power": 8000, "duration": 60},
        {"start": "19:00", "power": 4000, "duration": 60},
    ]


def test_build_discharge_schedule_length_mismatch():
    logger.info("schedule_builder: validates schedule length alignment")
    periods = [{"start": "18:00"}]
    with pytest.raises(ValueError):
        build_discharge_schedule(periods, power_ranks=[8000, 4000], duration_minutes=60)


def test_merge_schedules_overlap():
    logger.info("schedule_builder: charge takes priority on overlap")
    charge = [{"start": "01:00", "power": 8000, "duration": 60}]
    discharge = [
        {"start": "01:00", "power": 4000, "duration": 60},
        {"start": "18:00", "power": 4000, "duration": 60},
    ]

    merged = merge_schedules(charge, discharge)
    assert merged == {
        "charge": charge,
        "discharge": [{"start": "18:00", "power": 4000, "duration": 60}],
    }


def test_merge_schedules_no_overlap():
    logger.info("schedule_builder: merges without overlap")
    charge = [{"start": "01:00", "power": 8000, "duration": 60}]
    discharge = [{"start": "18:00", "power": 4000, "duration": 60}]

    merged = merge_schedules(charge, discharge)
    assert merged == {"charge": charge, "discharge": discharge}
