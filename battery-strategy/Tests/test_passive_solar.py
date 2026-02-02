import unittest
from unittest.mock import MagicMock
import logging
import sys
import os

# Add app to path
sys.path.append(os.path.join(os.path.dirname(__file__), 'app'))

from solar_monitor import SolarMonitor

# Mock HA State object
class State:
    def __init__(self, state_val):
        self.state = str(state_val)

class TestPassiveSolar(unittest.TestCase):
    def setUp(self):
        logging.basicConfig(level=logging.DEBUG)
        self.logger = logging.getLogger("Test")
        self.config = {
            "power_production_entity": "solar",
            "power_net_entity": "net",
            "passive_solar_entry_threshold": 1000,
            "passive_solar_exit_threshold": 200,
            "passive_solar_enabled": True
        }
        self.monitor = SolarMonitor(self.config, self.logger)
        self.ha_api = MagicMock()

    def set_states(self, solar, net):
        def get_state(entity_id):
            if entity_id == "solar": return State(solar)
            if entity_id == "net": return State(net)
            return None
        self.ha_api.get_state.side_effect = get_state

    def test_logic_sequence(self):
        print("\n--- Testing Passive Solar Logic Sequence ---")

        # 1. Normal State (Importing 500W, Solar 0)
        # Net > 0 = Import.
        self.set_states(solar=0, net=500)
        is_passive = self.monitor.check_passive_state(self.ha_api)
        print(f"1. Import 500W: Passive={is_passive} (Expected: False)")
        self.assertFalse(is_passive)

        # 2. Solar starts, but Net still importing (Solar 500, Net 200)
        self.set_states(solar=500, net=200)
        is_passive = self.monitor.check_passive_state(self.ha_api)
        print(f"2. Import 200W: Passive={is_passive} (Expected: False)")
        self.assertFalse(is_passive)

        # 3. High Export (Solar 2000, Net -1200) -> Entry > 1000
        self.set_states(solar=2000, net=-1200)
        is_passive = self.monitor.check_passive_state(self.ha_api)
        print(f"3. Export 1200W: Passive={is_passive} (Expected: True)")
        self.assertTrue(is_passive)

        # 4. Moderate Export (Solar 1500, Net -600) -> Hysteresis (Stay True)
        # Entry requires > 1000, but Exit requires Import > 200
        # -600 is not Import > 200.
        self.set_states(solar=1500, net=-600)
        is_passive = self.monitor.check_passive_state(self.ha_api)
        print(f"4. Export 600W (Hysteresis): Passive={is_passive} (Expected: True)")
        self.assertTrue(is_passive)

        # 5. Low Export (Solar 1200, Net -100) -> Still True
        self.set_states(solar=1200, net=-100)
        is_passive = self.monitor.check_passive_state(self.ha_api)
        print(f"5. Export 100W: Passive={is_passive} (Expected: True)")
        self.assertTrue(is_passive)

        # 6. Small Import (Solar 1000, Net 100) -> Wait, threshold 200
        # Start importing 100W. 100 < 200. Should stay True?
        # Logic says Exit if Net > 200.
        self.set_states(solar=1000, net=100)
        is_passive = self.monitor.check_passive_state(self.ha_api)
        print(f"6. Import 100W: Passive={is_passive} (Expected: True / Hysteresis)")
        self.assertTrue(is_passive)

        # 7. High Import (Solar 500, Net 300) -> Exit > 200
        self.set_states(solar=500, net=300)
        is_passive = self.monitor.check_passive_state(self.ha_api)
        print(f"7. Import 300W: Passive={is_passive} (Expected: False)")
        self.assertFalse(is_passive)

        # 8. Reset, Try Low Solar Exit Condition
        # Go Active check
        self.set_states(solar=2000, net=-1500)
        self.assertTrue(self.monitor.check_passive_state(self.ha_api))
        
        # Drop Solar < 200, even if Net is exporting (maybe impossible physically unless Load drops, but logic check)
        # Logic: if solar < 200 -> Exit.
        self.set_states(solar=100, net=-50) 
        is_passive = self.monitor.check_passive_state(self.ha_api)
        print(f"8. Solar 100W (Low)): Passive={is_passive} (Expected: False)")
        self.assertFalse(is_passive)

if __name__ == '__main__':
    unittest.main()
