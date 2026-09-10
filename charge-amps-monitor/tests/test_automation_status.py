from datetime import date, datetime

from app.automation import (
    AutomationConfig,
    AutomationStatus,
    ChargingAutomationCoordinator,
)
from app.price_slot_analyzer import DailyPriceAnalysis


class _Ha:
    pass


class _SchedulePort:
    def upsert_schedule(self, **kwargs):
        raise AssertionError("No schedule should be written when no slots qualify")

    def get_schedules(self, charge_point_id):
        return []


class _Analyzer:
    def analyze_today(self):
        return self._analysis()

    def analyze_tomorrow(self):
        return self._analysis()

    @staticmethod
    def _analysis():
        return DailyPriceAnalysis(
            target_date=date.today(),
            all_slots=[],
            cheapest_slots=[],
            min_price=0.21,
            max_price=0.30,
            avg_price=0.25,
            price_threshold=0.20,
            slots_filtered_by_threshold=96,
        )


def test_valid_price_data_without_qualifying_slots_is_not_price_sensor_error():
    coordinator = ChargingAutomationCoordinator(
        _SchedulePort(),
        _Ha(),
        AutomationConfig(
            enabled=True,
            operation_mode="standalone",
            price_entity_id="sensor.energy_prices_electricity_import_price",
            top_x_charge_count=80,
            price_threshold=0.20,
            max_current_per_phase=12,
            connector_id=1,
            timezone="Europe/Amsterdam",
        ),
    )
    coordinator._analyzer = _Analyzer()

    status = coordinator.tick(
        now=datetime(2026, 9, 10, 13, 0, tzinfo=coordinator._tz),
        charge_point_id="charger-1",
    )

    assert status.state == "waiting_for_prices"
    assert status.message == "No qualifying charging slots"
    assert status.last_error is None
    assert status.plan_date == "2026-09-10"
    assert status.attributes["price_data_available"] is True
