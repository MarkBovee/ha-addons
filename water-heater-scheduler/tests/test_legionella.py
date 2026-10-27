import sys
import unittest
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import legionella
from app.heating_plan import build_heating_plan
from app.main import get_lowest_price_window
from app.models import HeaterState, ScheduleConfig

SATURDAY = 5
# The run of Saturday 17 Oct 2026 started at 13:00; the water stayed above 60 °C, so the last recording is 18:30.
LAST_RUN = datetime(2026, 10, 17, 18, 30)


class LegionellaDueTests(unittest.TestCase):
    """The protection is due on calendar days, not on elapsed hours."""

    def test_the_next_saturday_is_due_although_the_last_recording_was_late_in_the_evening(self):
        """Intent: seven calendar days after the day of the last run the protection is due, at any hour of that day.
        Why: on 24 Oct 14:00 the old rule counted 6 days 19.5 hours as 6 days and skipped the run, which left a gap of 14 days."""
        self.assertTrue(legionella.is_due(LAST_RUN, date(2026, 10, 24)))
        self.assertFalse(legionella.is_due(LAST_RUN, date(2026, 10, 23)))
        decision = legionella.decide(LAST_RUN, datetime(2026, 10, 24, 14, 0), SATURDAY, after_night_window=True)
        self.assertTrue(decision.is_day and decision.needs and decision.use)

    def test_a_protection_that_never_ran_is_due_at_once(self):
        """Intent: no recorded run means due.
        Why: an installation without history must run the protection on its first chosen weekday instead of waiting a week."""
        self.assertTrue(legionella.is_due(None, date(2026, 10, 27)))
        self.assertTrue(legionella.decide(None, datetime(2026, 10, 31, 13, 0), SATURDAY, after_night_window=True).use)

    def test_the_state_uses_the_same_rule(self):
        """Intent: HeaterState.needs_legionella_protection follows the calendar-day rule for a given day.
        Why: the heating plan reads this method, so it must agree with the evaluation that runs the protection."""
        state = HeaterState()
        state.set_last_legionella_protection(LAST_RUN)
        self.assertTrue(state.needs_legionella_protection(7, today=date(2026, 10, 24)))
        self.assertFalse(state.needs_legionella_protection(7, today=date(2026, 10, 23)))


class LegionellaScheduleTests(unittest.TestCase):
    """The protection runs on the chosen weekday only."""

    def test_other_weekdays_never_run_it_even_when_it_is_overdue(self):
        """Intent: on days other than the chosen weekday the protection does not run, however long it has been.
        Why: the owner wants it on the legionella day only; a missed Saturday waits for the next one."""
        for day in (25, 26, 27, 28, 29, 30):
            decision = legionella.decide(LAST_RUN, datetime(2026, 10, day, 13, 0), SATURDAY, after_night_window=True)
            self.assertTrue(decision.needs)
            self.assertFalse(decision.use or decision.is_day, f"{day} Oct")
        again = legionella.decide(LAST_RUN, datetime(2026, 10, 31, 13, 0), SATURDAY, after_night_window=True)
        self.assertTrue(again.use)

    def test_the_night_window_never_runs_the_protection(self):
        """Intent: before the end of the night window the scheduled day does not run it either.
        Why: the night program has its own rules; the protection belongs in the day window."""
        night = legionella.decide(LAST_RUN, datetime(2026, 10, 24, 4, 0), SATURDAY, after_night_window=False)
        self.assertTrue(night.needs)
        self.assertFalse(night.use or night.is_day)

    def test_the_heating_plan_gives_only_the_scheduled_day_the_long_window(self):
        """Intent: the published plan shows a legionella window on the chosen weekday when due, and a normal one on other days.
        Why: the plan tells the energy manager when the heat pump runs; it must match what the scheduler will do."""
        config = ScheduleConfig(water_heater_entity_id="water_heater.test")
        tuesday, saturday = date(2026, 10, 27), date(2026, 10, 31)
        prices = lambda day: {datetime(day.year, day.month, day.day, hour): 0.30 - (0.05 if 13 <= hour < 16 else 0) for hour in range(24)}
        now = datetime(2026, 10, 27, 9, 0)
        plan = build_heating_plan(config, {tuesday: prices(tuesday), saturday: prices(saturday)}, now, get_lowest_price_window,
                                  legionella_due=True, legionella_weekday=SATURDAY)
        self.assertEqual([w.kind for w in plan], ["day", "legionella"])
        self.assertEqual((plan[1].end - plan[1].start).total_seconds() / 3600, config.legionella_duration_hours)


if __name__ == "__main__":
    unittest.main()
