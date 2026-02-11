import logging
import datetime


class GapScheduler:
    def __init__(self, logger: logging.Logger):
        self.logger = logger

    def generate_passive_gap_schedule(self) -> dict:
        """Generate a schedule dict for 'Passive Solar' mode.

        Format:
        - Timeslot 1 (Now + 1 min): Charge 0W (The Gap)
        - Timeslot 2 (Now + 2 mins): Discharge (Safety fallback)
        (The inverter will self-consume solar during the gap)
        """
        now = datetime.datetime.now(datetime.timezone.utc)

        gap_start = now + datetime.timedelta(minutes=1)
        start_str = gap_start.strftime("%H:%M")

        fallback_start = now + datetime.timedelta(minutes=2)
        fallback_str = fallback_start.strftime("%H:%M")

        return {
            "charge": [
                {
                    "start": start_str,
                    "duration": 1,
                    "power": 0,
                }
            ],
            "discharge": [
                {
                    "start": fallback_str,
                    "duration": 60,
                    "power": 4000,
                }
            ],
        }
