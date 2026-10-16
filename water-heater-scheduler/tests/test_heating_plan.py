import sys
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import main
from app.heating_plan import DAY, LEGIONELLA, NIGHT, build_heating_plan, plan_attributes, plan_state
from app.models import HeaterState, ScheduleConfig

# Hourly import prices of 15 Oct 2026 (a Thursday); the cheapest hour is 13:00, the cheapest night hour 04:00.
THURSDAY = [0.364, 0.358, 0.343, 0.339, 0.335, 0.346, 0.387, 0.426, 0.444, 0.397, 0.368, 0.312, 0.259, 0.236, 0.241, 0.278, 0.34, 0.408, 0.435, 0.424, 0.39, 0.386, 0.379, 0.366]


def prices_of(day: date, hourly=THURSDAY) -> dict:
    """An hourly price curve of one day keyed by local hour start, like the scheduler parses it."""
    return {datetime(day.year, day.month, day.day, hour): price for hour, price in enumerate(hourly)}


def config(**changes) -> ScheduleConfig:
    """The default configuration with the water heater entity set."""
    return ScheduleConfig(water_heater_entity_id="water_heater.test", **changes)


NOW = datetime(2026, 10, 15, 9, 30)
TODAY, TOMORROW = date(2026, 10, 15), date(2026, 10, 16)


class HeatingPlanTests(unittest.TestCase):
    def test_a_day_is_planned_in_its_cheapest_hour_with_the_configured_energy(self):
        plan = build_heating_plan(config(), {TODAY: prices_of(TODAY)}, NOW, main.get_lowest_price_window)
        self.assertEqual(len(plan), 1)
        window = plan[0]
        self.assertEqual((window.kind, window.start, window.end, window.energy_kwh), (DAY, datetime(2026, 10, 15, 13), datetime(2026, 10, 15, 14), 1.9))
        self.assertAlmostEqual(window.avg_price, 0.236)

    def test_today_and_tomorrow_each_get_a_window_once_tomorrows_prices_are_known(self):
        plan = build_heating_plan(config(), {TODAY: prices_of(TODAY), TOMORROW: prices_of(TOMORROW)}, NOW, main.get_lowest_price_window)
        self.assertEqual([w.start.day for w in plan], [15, 16])

    def test_a_window_that_has_ended_is_dropped_and_one_that_is_running_is_kept(self):
        late = datetime(2026, 10, 15, 14, 30)
        self.assertEqual(build_heating_plan(config(), {TODAY: prices_of(TODAY)}, late, main.get_lowest_price_window), [])
        running = build_heating_plan(config(), {TODAY: prices_of(TODAY)}, datetime(2026, 10, 15, 13, 20), main.get_lowest_price_window)
        self.assertEqual(len(running), 1)

    def test_the_night_window_wins_when_it_is_cheaper_and_has_its_own_energy_setting(self):
        cheap_night = [0.10] * 6 + THURSDAY[6:]
        plan = build_heating_plan(config(night_heating_energy_kwh=0.5), {TODAY: prices_of(TODAY, cheap_night)}, datetime(2026, 10, 15, 0, 5), main.get_lowest_price_window)
        self.assertEqual((plan[0].kind, plan[0].energy_kwh), (NIGHT, 0.5))
        silent = build_heating_plan(config(), {TODAY: prices_of(TODAY, cheap_night)}, datetime(2026, 10, 15, 0, 5), main.get_lowest_price_window)
        self.assertEqual(silent, [], "night heating defaults to 0 kWh: nothing to plan")

    def test_the_legionella_day_gets_the_long_window_and_its_energy(self):
        saturday = date(2026, 10, 17)
        plan = build_heating_plan(config(), {saturday: prices_of(saturday)}, datetime(2026, 10, 17, 8), main.get_lowest_price_window)
        window = plan[0]
        self.assertEqual((window.kind, window.energy_kwh, window.end - window.start), (LEGIONELLA, 2.6, timedelta(hours=3)))
        not_due = build_heating_plan(config(), {saturday: prices_of(saturday)}, datetime(2026, 10, 17, 8), main.get_lowest_price_window, legionella_due=False)
        self.assertEqual((not_due[0].kind, not_due[0].energy_kwh), (DAY, 1.9))

    def test_nothing_is_planned_while_away_and_without_prices(self):
        self.assertEqual(build_heating_plan(config(), {TODAY: prices_of(TODAY)}, NOW, main.get_lowest_price_window, away=True), [])
        self.assertEqual(build_heating_plan(config(), {TODAY: {}, TOMORROW: {}}, NOW, main.get_lowest_price_window), [])

    def test_the_entity_state_is_the_next_start_and_the_attributes_list_every_window(self):
        plan = build_heating_plan(config(heating_energy_kwh=2.2), {TODAY: prices_of(TODAY), TOMORROW: prices_of(TOMORROW)}, NOW, main.get_lowest_price_window)
        attributes = plan_attributes(plan, config(heating_energy_kwh=2.2))
        self.assertTrue(plan_state(plan).startswith("2026-10-15T13:00"))
        self.assertEqual([(w["kind"], w["energy_kwh"]) for w in attributes["windows"]], [(DAY, 2.2), (DAY, 2.2)])
        self.assertTrue(attributes["windows"][0]["start"].startswith("2026-10-15T13:00") and attributes["windows"][0]["end"].startswith("2026-10-15T14:00"))
        self.assertEqual((plan_state([]), attributes["heating_energy_kwh"]), ("none", 2.2))


class FakeApi:
    """Records the states the add-on posts."""
    def __init__(self):
        self.posts = []

    def create_or_update_entity(self, entity_id, state, attributes, log_success=False):
        self.posts.append((entity_id, state, attributes))


class FakeReader:
    """An entity reader that says nothing is on."""
    def is_entity_on(self, entity_id):
        return False


class PublishTests(unittest.TestCase):
    def setUp(self):
        main._previous_plan.update(signature=None, at=None)
        self.state = HeaterState()

    def publish(self, api, now, prices_tomorrow=None):
        main.publish_heating_plan(config(), api, FakeReader(), self.state, prices_of(TODAY), prices_tomorrow or {}, now)

    def test_the_plan_is_posted_once_and_again_only_when_it_changes_or_after_an_hour(self):
        api = FakeApi()
        self.publish(api, NOW)
        self.publish(api, NOW + timedelta(minutes=5))
        self.assertEqual(len(api.posts), 1)
        self.assertEqual(api.posts[0][0], "sensor.wh_heating_plan")
        self.publish(api, NOW + timedelta(minutes=10), prices_of(TOMORROW))
        self.assertEqual(len(api.posts), 2, "tomorrow's prices arrived: the plan changed")
        self.publish(api, NOW + timedelta(minutes=75), prices_of(TOMORROW))
        self.assertEqual(len(api.posts), 3, "an hour later it is posted again: a REST state does not survive a Home Assistant restart")


if __name__ == "__main__":
    unittest.main()
