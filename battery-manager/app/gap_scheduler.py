import json
import logging
import datetime
import random

class GapScheduler:
    def __init__(self, logger: logging.Logger):
        self.logger = logger

    def generate_passive_gap_schedule(self) -> str:
        """
        Generate a JSON schedule for 'Passive Solar' mode.
        Format:
        - Timeslot 1 (Now + 1 min): Charge 0W (The Gap)
        - Timeslot 2 (Now + 2 mins): Discharge (Safety fallback)
        (The inverter will self-consume solar during the gap)
        """
        now = datetime.datetime.now()
        
        # Start gap 1 minute from now to allow processing
        gap_start = now + datetime.timedelta(minutes=1)
        start_str = gap_start.strftime("%H:%M")
        
        # Safety discharge shortly after
        fallback_start = now + datetime.timedelta(minutes=2)
        fallback_str = fallback_start.strftime("%H:%M")

        schedule = {
            "charge": [
                {
                    "start": start_str,
                    "duration": 1, # 1 minute gap
                    "power": 0     # 0W charge = Idle/Self-consume
                }
            ],
            "discharge": [
                {
                    "start": fallback_str,
                    "duration": 60, # 1 hour fallback
                    "power": 4000   # Moderate discharge
                }
            ]
        }
        
        return json.dumps(schedule)
