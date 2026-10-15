"""Task F: publish to battery-api only when the published periods change."""

from copy import deepcopy
from datetime import datetime, timedelta, timezone

import pytest

from app import main as bm_main

NOW = datetime(2026, 10, 7, 16, 0, tzinfo=timezone.utc)


class _Mqtt:
    def __init__(self):
        self.payloads = []

    def is_connected(self):
        return True

    def publish_raw(self, topic, payload, retain=False):
        self.payloads.append(deepcopy(payload))
        return True


@pytest.fixture(autouse=True)
def _clock(monkeypatch):
    monkeypatch.setattr(bm_main, "_utcnow", lambda: NOW)


def _schedule(adaptive_power=1000, sell_power=8000):
    today = datetime.now().astimezone().replace(hour=19, minute=0, second=0, microsecond=0)
    return {
        "charge": [],
        "discharge": [
            {"start": today.isoformat(), "duration": 60, "power": sell_power, "window_type": "discharge"},
            {"start": (today + timedelta(hours=1)).isoformat(), "duration": 60,
             "power": adaptive_power, "window_type": "adaptive"},
        ],
    }


def _state():
    return bm_main.RuntimeState(schedule={"charge": [], "discharge": []}, schedule_generated_at=None)


def test_adaptive_steps_below_100w_do_not_republish():
    mqtt, state = _Mqtt(), _state()
    assert bm_main._publish_schedule(mqtt, _schedule(1000), False, state=state)
    assert bm_main._publish_schedule(mqtt, _schedule(1050), False, state=state)
    assert bm_main._publish_schedule(mqtt, _schedule(1099), False, state=state)
    assert len(mqtt.payloads) == 1

    assert bm_main._publish_schedule(mqtt, _schedule(1100), False, state=state)
    assert len(mqtt.payloads) == 2


def test_steps_are_measured_against_the_last_published_power():
    mqtt, state = _Mqtt(), _state()
    bm_main._publish_schedule(mqtt, _schedule(1000), False, state=state)
    for power in (1060, 1090, 1010):  # drift without ever reaching +100 W
        bm_main._publish_schedule(mqtt, _schedule(power), False, state=state)
    assert len(mqtt.payloads) == 1


def test_scheduled_sell_power_changes_always_publish():
    mqtt, state = _Mqtt(), _state()
    bm_main._publish_schedule(mqtt, _schedule(sell_power=8000), False, state=state)
    bm_main._publish_schedule(mqtt, _schedule(sell_power=7950), False, state=state)  # not adaptive
    assert len(mqtt.payloads) == 2


def test_period_set_changes_publish():
    mqtt, state = _Mqtt(), _state()
    bm_main._publish_schedule(mqtt, _schedule(), False, state=state)
    changed = _schedule()
    changed["discharge"][0]["duration"] = 45
    bm_main._publish_schedule(mqtt, changed, False, state=state)
    assert len(mqtt.payloads) == 2


def test_force_and_heartbeat_republish_unchanged_content(monkeypatch):
    mqtt, state = _Mqtt(), _state()
    bm_main._publish_schedule(mqtt, _schedule(), False, state=state)
    bm_main._publish_schedule(mqtt, _schedule(), False, state=state, force=True)
    assert len(mqtt.payloads) == 2

    later = NOW + timedelta(seconds=bm_main.PUBLISH_HEARTBEAT_SECONDS)
    monkeypatch.setattr(bm_main, "_utcnow", lambda: later)
    bm_main._publish_schedule(mqtt, _schedule(), False, state=state)
    assert len(mqtt.payloads) == 3


def test_failed_publish_is_retried_next_time(monkeypatch):
    class _Down(_Mqtt):
        def is_connected(self):
            return False

    monkeypatch.setattr("time.sleep", lambda _seconds: None)
    state = _state()

    assert not bm_main._publish_schedule(_Down(), _schedule(), False, state=state)
    assert state.last_published_api is None

    mqtt = _Mqtt()
    assert bm_main._publish_schedule(mqtt, _schedule(), False, state=state)
    assert len(mqtt.payloads) == 1
