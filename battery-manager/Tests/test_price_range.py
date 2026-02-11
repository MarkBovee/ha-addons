"""Tests for _determine_price_range and charging_price_threshold logic."""

import sys
import os
import pytest

# Ensure the battery-manager root is on the path so 'app' and 'shared' resolve
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.price_analyzer import PriceRange
from app.main import _determine_price_range


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def load_range():
    return PriceRange(min_price=0.05, max_price=0.15)


@pytest.fixture
def discharge_range():
    return PriceRange(min_price=0.30, max_price=0.50)


# ---------------------------------------------------------------------------
# Without threshold (original behaviour)
# ---------------------------------------------------------------------------

class TestDetermineRangeWithoutThreshold:
    def test_load_when_import_in_load_range(self, load_range, discharge_range):
        result = _determine_price_range(0.10, 0.10, load_range, discharge_range)
        assert result == "load"

    def test_discharge_when_export_in_discharge_range(self, load_range, discharge_range):
        result = _determine_price_range(0.25, 0.35, load_range, discharge_range)
        assert result == "discharge"

    def test_adaptive_when_neither(self, load_range, discharge_range):
        result = _determine_price_range(0.20, 0.20, load_range, discharge_range)
        assert result == "adaptive"

    def test_load_takes_precedence_over_discharge(self, load_range, discharge_range):
        """Import in load range, export in discharge range -> load wins."""
        result = _determine_price_range(0.10, 0.40, load_range, discharge_range)
        assert result == "load"

    def test_none_ranges_give_adaptive(self):
        result = _determine_price_range(0.20, 0.20, None, None)
        assert result == "adaptive"


# ---------------------------------------------------------------------------
# With charging_price_threshold
# ---------------------------------------------------------------------------

class TestDetermineRangeWithThreshold:
    def test_passive_below_threshold(self, load_range, discharge_range):
        """Price in adaptive range but below threshold -> passive."""
        result = _determine_price_range(
            0.20, 0.20, load_range, discharge_range, charging_price_threshold=0.26,
        )
        assert result == "passive"

    def test_adaptive_above_threshold(self, load_range, discharge_range):
        """Price in adaptive range and above threshold -> adaptive."""
        result = _determine_price_range(
            0.28, 0.28, load_range, discharge_range, charging_price_threshold=0.26,
        )
        assert result == "adaptive"

    def test_load_still_wins_over_threshold(self, load_range, discharge_range):
        """Import in load range -> load, regardless of threshold."""
        result = _determine_price_range(
            0.10, 0.10, load_range, discharge_range, charging_price_threshold=0.26,
        )
        assert result == "load"

    def test_discharge_still_wins_over_threshold(self, load_range, discharge_range):
        """Export in discharge range -> discharge, regardless of threshold."""
        result = _determine_price_range(
            0.25, 0.35, load_range, discharge_range, charging_price_threshold=0.26,
        )
        assert result == "discharge"

    def test_exact_threshold_is_adaptive(self, load_range, discharge_range):
        """Price exactly at threshold -> adaptive (not passive)."""
        result = _determine_price_range(
            0.26, 0.26, load_range, discharge_range, charging_price_threshold=0.26,
        )
        assert result == "adaptive"

    def test_threshold_none_gives_adaptive(self, load_range, discharge_range):
        """No threshold set -> adaptive, not passive."""
        result = _determine_price_range(
            0.20, 0.20, load_range, discharge_range, charging_price_threshold=None,
        )
        assert result == "adaptive"
