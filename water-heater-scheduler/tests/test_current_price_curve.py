import sys
import unittest
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.main import get_current_price_from_sensor_state


class CurrentPriceCurveTests(unittest.TestCase):
    def test_get_current_price_from_sensor_state_prefers_active_curve_entry(self):
        sensor_state = {
            "state": "0.27",
            "attributes": {
                "price_curve": [
                    {
                        "start": "2026-05-01T11:00:00+00:00",
                        "end": "2026-05-01T12:00:00+00:00",
                        "price": -0.47,
                    }
                ]
            },
        }

        now = datetime.fromisoformat("2026-05-01T13:30:00+02:00")

        self.assertEqual(get_current_price_from_sensor_state(sensor_state, now), -0.47)


if __name__ == "__main__":
    unittest.main()
