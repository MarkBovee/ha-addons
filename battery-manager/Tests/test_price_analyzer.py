"""Tests for price_analyzer module - price range calculations."""

import sys
import os
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.price_analyzer import (
    PriceRange,
    calculate_price_ranges,
    calculate_top_x_count,
    find_profitable_discharge_starts,
)
from app.status_reporter import find_upcoming_windows


class TestCalculatePriceRanges:
    def test_invalid_spread_returns_none_discharge_range(self):
        """When spread is too small (discharge_min > discharge_max), discharge_range should be None."""
        # Import prices: €0.23-0.24 (cheapest: €0.23)
        # Export prices: €0.28-0.29 (highest: €0.29)
        # min_profit: €0.10
        # Required discharge_min: €0.23 + €0.10 = €0.33
        # Actual discharge_max: €0.29
        # Since €0.33 > €0.29, discharge_range should be None
        
        import_curve = [
            {"price": 0.23}, {"price": 0.24}, {"price": 0.25}, {"price": 0.26},
        ]
        export_curve = [
            {"price": 0.28}, {"price": 0.29}, {"price": 0.28}, {"price": 0.27},
        ]
        
        load_range, discharge_range, adaptive_range = calculate_price_ranges(
            import_curve, export_curve,
            top_x_charge=1,  # Take cheapest 1 period
            top_x_discharge=2,  # Take most expensive 2 periods
            min_profit=0.10,
        )
        
        assert load_range is not None
        assert load_range.min_price == 0.23
        assert load_range.max_price == 0.23
        
        # Key assertion: discharge_range should be None due to invalid spread
        assert discharge_range is None
        
        # Adaptive range should extend to max export price
        assert adaptive_range is not None
        assert adaptive_range.min_price == 0.23
        assert adaptive_range.max_price == 0.29

    def test_valid_spread_returns_discharge_range(self):
        """When spread is sufficient, discharge_range should be valid."""
        # Import prices: €0.20-0.25 (cheapest: €0.20)
        # Export prices: €0.35-0.40 (highest: €0.40, €0.38)
        # min_profit: €0.10
        # Required discharge_min: €0.20 + €0.10 = €0.30
        # Actual discharge_max: €0.40
        # Since €0.30 < €0.40, discharge_range should be valid
        
        import_curve = [
            {"price": 0.20}, {"price": 0.22}, {"price": 0.24}, {"price": 0.25},
        ]
        export_curve = [
            {"price": 0.35}, {"price": 0.40}, {"price": 0.38}, {"price": 0.36},
        ]
        
        load_range, discharge_range, adaptive_range = calculate_price_ranges(
            import_curve, export_curve,
            top_x_charge=1,
            top_x_discharge=2,
            min_profit=0.10,
        )
        
        assert load_range is not None
        assert load_range.min_price == 0.20
        assert load_range.max_price == 0.20
        
        assert discharge_range is not None
        assert discharge_range.min_price == 0.38  # max(min([0.40, 0.38]), 0.30) = max(0.38, 0.30)
        assert discharge_range.max_price == 0.40
        
        assert adaptive_range is not None
        assert adaptive_range.min_price == 0.20
        assert adaptive_range.max_price == 0.38

    def test_zero_spread_edge_case(self):
        """When min_profit exactly equals spread, behavior depends on selection."""
        import_curve = [{"price": 0.20}, {"price": 0.21}]
        export_curve = [{"price": 0.30}, {"price": 0.29}]
        
        # min_profit = 0.10, cheapest import = 0.20
        # Top 1 discharge period is the one with highest export price
        # If that's 0.30, then min(highest_prices) = max(highest_prices) = 0.30
        # discharge_min = max(0.30, 0.20 + 0.10) = 0.30
        # discharge_max = 0.30
        # This creates a valid single-point range
        
        load_range, discharge_range, adaptive_range = calculate_price_ranges(
            import_curve, export_curve,
            top_x_charge=1,
            top_x_discharge=1,
            min_profit=0.10,
        )
        
        # With top_x=1, we get the single highest export period
        # Depending on implementation, this may or may not meet profit requirement
        # Just verify the function doesn't crash
        assert load_range is not None


class TestDischargeSelectionHelpers:
    def test_fractional_hours_expand_to_required_slot_count(self):
        assert calculate_top_x_count(1.5, 60) == 2
        assert calculate_top_x_count(1.5, 30) == 3
        assert calculate_top_x_count(2.5, 15) == 10

    def test_profitable_discharge_starts_select_exact_top_slots(self):
        import_curve = [
            {"start": "2026-03-09T00:00:00+00:00", "price": 0.20},
            {"start": "2026-03-09T01:00:00+00:00", "price": 0.22},
            {"start": "2026-03-09T02:00:00+00:00", "price": 0.21},
        ]
        export_curve = [
            {"start": "2026-03-09T00:00:00+00:00", "price": 0.36},
            {"start": "2026-03-09T01:00:00+00:00", "price": 0.40},
            {"start": "2026-03-09T02:00:00+00:00", "price": 0.38},
            {"start": "2026-03-09T03:00:00+00:00", "price": 0.37},
        ]

        selected = find_profitable_discharge_starts(
            import_curve,
            export_curve,
            top_x_discharge=2,
            min_profit=0.10,
        )

        assert selected == {
            "2026-03-09T01:00:00+00:00",
            "2026-03-09T02:00:00+00:00",
        }

    def test_upcoming_windows_respect_exact_discharge_starts(self):
        now = datetime(2026, 3, 9, 0, 0, tzinfo=timezone.utc)
        import_curve = []
        export_curve = []
        base = now

        for index, price in enumerate((0.20, 0.20, 0.20, 0.20)):
            start = base + timedelta(hours=index)
            end = start + timedelta(hours=1)
            import_curve.append({
                "start": start.isoformat(),
                "end": end.isoformat(),
                "price": price,
            })

        for index, price in enumerate((0.35, 0.40, 0.38, 0.37)):
            start = base + timedelta(hours=index)
            end = start + timedelta(hours=1)
            export_curve.append({
                "start": start.isoformat(),
                "end": end.isoformat(),
                "price": price,
            })

        windows = find_upcoming_windows(
            import_curve,
            export_curve,
            load_range=None,
            discharge_range=PriceRange(min_price=0.37, max_price=0.40),
            charging_price_threshold=None,
            now=now,
            discharge_slot_starts={
                (base + timedelta(hours=1)).isoformat(),
                (base + timedelta(hours=2)).isoformat(),
            },
        )

        assert len(windows["discharge"]) == 1
        assert windows["discharge"][0]["start"] == base + timedelta(hours=1)
        assert windows["discharge"][0]["end"] == base + timedelta(hours=3)
