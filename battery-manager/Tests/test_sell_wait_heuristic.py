"""Tests for deferred sell-window heuristic in main schedule generation."""

import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.main import _get_sell_wait_decision


def _window(start: datetime, end: datetime, avg_price: float) -> dict:
    return {"start": start, "end": end, "avg_price": avg_price}


def test_sell_wait_decision_when_future_morning_price_is_better():
    now = datetime(2026, 3, 8, 18, 0, tzinfo=timezone.utc)
    windows = [
        _window(now + timedelta(hours=1), now + timedelta(hours=2), 0.33),
        _window(now + timedelta(hours=12), now + timedelta(hours=13), 0.40),
    ]
    heuristics = {
        "sell_wait_for_better_morning_enabled": True,
        "sell_wait_horizon_hours": 12,
        "sell_wait_min_gain_threshold": 0.03,
        "sell_wait_morning_start_hour": 5,
        "sell_wait_morning_end_hour": 10,
    }

    decision = _get_sell_wait_decision(windows, now, heuristics)

    assert decision is not None
    assert decision["wait_until"] == now + timedelta(hours=12)
    assert round(decision["gain"], 3) == 0.07


def test_sell_wait_no_decision_when_gain_too_small():
    now = datetime(2026, 3, 8, 18, 0, tzinfo=timezone.utc)
    windows = [
        _window(now + timedelta(hours=1), now + timedelta(hours=2), 0.33),
        _window(now + timedelta(hours=12), now + timedelta(hours=13), 0.345),
    ]
    heuristics = {
        "sell_wait_for_better_morning_enabled": True,
        "sell_wait_horizon_hours": 12,
        "sell_wait_min_gain_threshold": 0.02,
        "sell_wait_morning_start_hour": 5,
        "sell_wait_morning_end_hour": 10,
    }

    decision = _get_sell_wait_decision(windows, now, heuristics)

    assert decision is None


def test_sell_wait_no_decision_when_target_outside_horizon():
    now = datetime(2026, 3, 8, 18, 0, tzinfo=timezone.utc)
    windows = [
        _window(now + timedelta(hours=1), now + timedelta(hours=2), 0.33),
        _window(now + timedelta(hours=13), now + timedelta(hours=14), 0.40),
    ]
    heuristics = {
        "sell_wait_for_better_morning_enabled": True,
        "sell_wait_horizon_hours": 12,
        "sell_wait_min_gain_threshold": 0.03,
        "sell_wait_morning_start_hour": 5,
        "sell_wait_morning_end_hour": 10,
    }

    decision = _get_sell_wait_decision(windows, now, heuristics)

    assert decision is None


def test_sell_wait_no_decision_when_disabled():
    now = datetime(2026, 3, 8, 18, 0, tzinfo=timezone.utc)
    windows = [
        _window(now + timedelta(hours=1), now + timedelta(hours=2), 0.33),
        _window(now + timedelta(hours=12), now + timedelta(hours=13), 0.40),
    ]
    heuristics = {
        "sell_wait_for_better_morning_enabled": False,
    }

    decision = _get_sell_wait_decision(windows, now, heuristics)

    assert decision is None


def test_sell_wait_exact_threshold_triggers_defer():
    now = datetime(2026, 3, 8, 18, 0, tzinfo=timezone.utc)
    windows = [
        _window(now + timedelta(hours=1), now + timedelta(hours=2), 0.33),
        _window(now + timedelta(hours=12), now + timedelta(hours=13), 0.35),
    ]
    heuristics = {
        "sell_wait_for_better_morning_enabled": True,
        "sell_wait_horizon_hours": 12,
        "sell_wait_min_gain_threshold": 0.02,
        "sell_wait_morning_start_hour": 5,
        "sell_wait_morning_end_hour": 10,
    }

    decision = _get_sell_wait_decision(windows, now, heuristics)

    assert decision is not None
    assert decision["wait_until"] == now + timedelta(hours=12)
