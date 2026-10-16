import os
import sys
import time
import unittest
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import main

# Hourly consumer prices of Thursday 15 Oct 2026 (local hours 00-23); 13:00 is the cheapest hour of the day part.
THURSDAY = [0.30, 0.29, 0.28, 0.28, 0.29, 0.31, 0.34, 0.37, 0.36, 0.33, 0.30, 0.27, 0.25, 0.236, 0.26, 0.29,
            0.33, 0.40, 0.46, 0.44, 0.39, 0.35, 0.32, 0.31]


class PriceCurveTimeZoneTests(unittest.TestCase):
    """The energy-prices curve is in UTC; the heating windows are chosen on local hours."""

    def setUp(self):
        """Run in the Amsterdam time zone, as the add-on does at home."""
        self._tz = os.environ.get("TZ")
        os.environ["TZ"] = "Europe/Amsterdam"
        time.tzset()

    def tearDown(self):
        """Put the process time zone back."""
        if self._tz is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = self._tz
        time.tzset()

    def test_utc_hours_become_local_hours_so_the_cheapest_hour_is_the_cheapest_local_hour(self):
        """15 Oct 2026, CEST: the 13:00 local hour is 11:00 UTC. Stripping the offset would have called it 11:00 local."""
        first_utc = datetime(2026, 10, 14, 22)                         # local midnight is 22:00 UTC
        state = {"attributes": {"price_curve": [{"start": (first_utc + timedelta(hours=h)).isoformat() + "+00:00", "price": p}
                                                for h, p in enumerate(THURSDAY)]}}
        prices = main.parse_price_curve(state)
        self.assertEqual(prices[datetime(2026, 10, 15, 13)], 0.236)
        today = {dt: p for dt, p in prices.items() if dt.date() == datetime(2026, 10, 15).date()}
        self.assertEqual(len(today), 24, "a whole local day, not 22 hours of it plus two of the day before")
        self.assertEqual(main.get_lowest_price_window(today, 6, 24, datetime(2026, 10, 15), 1), (datetime(2026, 10, 15, 13), 0.236))


if __name__ == "__main__":
    unittest.main()
