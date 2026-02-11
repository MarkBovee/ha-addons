"""Tests for soc_guardian module."""

import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.soc_guardian import can_charge, can_discharge


class TestCanCharge:
    def test_below_max_allows_charge(self):
        assert can_charge(50.0, 100.0) is True

    def test_at_max_disallows(self):
        assert can_charge(100.0, 100.0) is False

    def test_above_max_disallows(self):
        assert can_charge(101.0, 100.0) is False


class TestCanDischarge:
    def test_above_conservative_allows(self):
        assert can_discharge(60.0, 5.0, 40.0, is_conservative=True) is True

    def test_below_min_blocks(self):
        assert can_discharge(4.0, 5.0, 40.0, is_conservative=False) is False

    def test_at_min_blocks(self):
        assert can_discharge(5.0, 5.0, 40.0, is_conservative=False) is False

    def test_above_min_non_conservative_allows(self):
        assert can_discharge(10.0, 5.0, 40.0, is_conservative=False) is True

    def test_below_conservative_with_flag_blocks(self):
        assert can_discharge(30.0, 5.0, 40.0, is_conservative=True) is False

    def test_below_conservative_without_flag_allows(self):
        assert can_discharge(30.0, 5.0, 40.0, is_conservative=False) is True
