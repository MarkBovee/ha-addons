import sys
import types
import unittest
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

astral_module = types.ModuleType("astral")
astral_module.LocationInfo = type("LocationInfo", (), {"__init__": lambda self, *args, **kwargs: None, "observer": object()})
astral_sun_module = types.ModuleType("astral.sun")
astral_sun_module.sun = lambda *args, **kwargs: {
    "sunrise": datetime(2026, 5, 1, 6, 0, tzinfo=ZoneInfo("UTC")),
    "sunset": datetime(2026, 5, 1, 18, 0, tzinfo=ZoneInfo("UTC")),
}
sys.modules.setdefault("astral", astral_module)
sys.modules.setdefault("astral.sun", astral_sun_module)

from app.main import get_current_interval_price
from app.models import PriceInterval


class CurrentPriceSelectionTests(unittest.TestCase):
    def test_get_current_interval_price_uses_active_dst_interval(self):
        intervals = [
            PriceInterval(
                start=datetime(2026, 5, 1, 10, 0, tzinfo=ZoneInfo("UTC")),
                end=datetime(2026, 5, 1, 11, 0, tzinfo=ZoneInfo("UTC")),
                price_eur_mwh=100,
            ),
            PriceInterval(
                start=datetime(2026, 5, 1, 11, 0, tzinfo=ZoneInfo("UTC")),
                end=datetime(2026, 5, 1, 12, 0, tzinfo=ZoneInfo("UTC")),
                price_eur_mwh=-250,
            ),
        ]

        now_utc = datetime(2026, 5, 1, 11, 30, tzinfo=ZoneInfo("UTC"))

        self.assertEqual(get_current_interval_price(intervals, now_utc), -0.25)


if __name__ == "__main__":
    unittest.main()
