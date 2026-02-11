"""Tests for gap_scheduler module."""

import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import logging
from app.gap_scheduler import GapScheduler


@pytest.fixture
def scheduler():
    return GapScheduler(logging.getLogger("test"))


class TestGapScheduler:
    def test_returns_dict_not_string(self, scheduler):
        result = scheduler.generate_passive_gap_schedule()
        assert isinstance(result, dict), f"Expected dict, got {type(result)}"

    def test_has_charge_and_discharge_keys(self, scheduler):
        result = scheduler.generate_passive_gap_schedule()
        assert "charge" in result
        assert "discharge" in result

    def test_charge_has_zero_power(self, scheduler):
        result = scheduler.generate_passive_gap_schedule()
        assert result["charge"][0]["power"] == 0

    def test_discharge_has_positive_power(self, scheduler):
        result = scheduler.generate_passive_gap_schedule()
        assert result["discharge"][0]["power"] > 0

    def test_start_times_are_strings(self, scheduler):
        result = scheduler.generate_passive_gap_schedule()
        assert isinstance(result["charge"][0]["start"], str)
        assert isinstance(result["discharge"][0]["start"], str)
