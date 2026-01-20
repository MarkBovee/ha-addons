import logging
from datetime import datetime, timedelta

from app.main import RuntimeState, generate_schedule, monitor_active_period

logger = logging.getLogger("battery-manager-tests")


class DummyHaApi:
    def __init__(self, states):
        self._states = states

    def get_entity_state(self, entity_id):
        return self._states.get(entity_id)


class DummyMqtt:
    def __init__(self):
        self.published = []

    def publish_raw(self, topic, payload, retain=False):
        self.published.append((topic, payload))


def test_generate_schedule_basic():
    logger.info("e2e: generates schedule from price curve")
    now = datetime.utcnow()
    price_curve = [
        {"start": now.isoformat(), "end": (now + timedelta(minutes=15)).isoformat(), "price": 0.10},
        {"start": (now + timedelta(minutes=15)).isoformat(), "end": (now + timedelta(minutes=30)).isoformat(), "price": 0.20},
        {"start": (now + timedelta(minutes=30)).isoformat(), "end": (now + timedelta(minutes=45)).isoformat(), "price": 0.05},
    ]

    ha_api = DummyHaApi(
        {
            "sensor.energy_prices_price_import": {
                "state": "0.10",
                "attributes": {"price_curve": price_curve},
            }
            ,
            "sensor.energy_prices_price_export": {
                "state": "0.05",
                "attributes": {"price_curve": price_curve},
            }
        }
    )
    mqtt = DummyMqtt()

    config = {
        "heuristics": {"top_x_charge_hours": 2, "top_x_discharge_hours": 1, "excess_solar_threshold": 1000},
        "power": {"max_charge_power": 8000, "max_discharge_power": 8000, "min_discharge_power": 4000},
        "soc": {"min_soc": 5, "conservative_soc": 40, "target_eod_soc": 20},
        "temperature_based_discharge": {"enabled": False, "thresholds": []},
        "ev_charger": {"enabled": False, "charging_threshold": 500, "entity_id": "sensor.ev"},
        "timing": {"update_interval": 3600, "monitor_interval": 60},
        "dry_run": False,
        "entities": {
            "price_curve_entity": "sensor.energy_prices_price_import",
            "export_price_curve_entity": "sensor.energy_prices_price_export",
            "soc_entity": "sensor.battery_api_state_of_charge",
            "grid_power_entity": "sensor.grid_power",
            "solar_power_entity": "sensor.solar_power",
            "house_load_entity": "sensor.house_load_power",
            "temperature_entity": "sensor.weather_forecast_temperature",
        },
        "mqtt_host": "core-mosquitto",
        "mqtt_port": 1883,
    }

    schedule = generate_schedule(config, ha_api, mqtt)

    assert len(schedule["charge"]) == 2
    assert len(schedule["discharge"]) == 1
    assert mqtt.published


def test_monitor_active_period_ev_pause():
    logger.info("e2e: pauses discharge when EV charging")
    now = datetime.utcnow()
    active_period = {"start": (now - timedelta(minutes=1)).isoformat(), "duration": 10, "power": 8000}

    state = RuntimeState(schedule={"charge": [], "discharge": [active_period]}, schedule_generated_at=now)

    ha_api = DummyHaApi(
        {
            "sensor.battery_api_state_of_charge": {"state": "60"},
            "sensor.grid_power": {"state": "100"},
            "sensor.solar_power": {"state": "0"},
            "sensor.house_load_power": {"state": "0"},
            "sensor.ev_charger_power": {"state": "1000"},
        }
    )

    mqtt = DummyMqtt()

    config = {
        "heuristics": {"top_x_charge_hours": 2, "top_x_discharge_hours": 1, "excess_solar_threshold": 1000},
        "power": {"max_charge_power": 8000, "max_discharge_power": 8000, "min_discharge_power": 4000},
        "soc": {"min_soc": 5, "conservative_soc": 40, "target_eod_soc": 20},
        "temperature_based_discharge": {"enabled": False, "thresholds": []},
        "ev_charger": {"enabled": True, "charging_threshold": 500, "entity_id": "sensor.ev_charger_power"},
        "timing": {"update_interval": 3600, "monitor_interval": 60},
        "dry_run": False,
        "entities": {
            "price_curve_entity": "sensor.energy_prices_price_import",
            "export_price_curve_entity": "sensor.energy_prices_price_export",
            "soc_entity": "sensor.battery_api_state_of_charge",
            "grid_power_entity": "sensor.grid_power",
            "solar_power_entity": "sensor.solar_power",
            "house_load_entity": "sensor.house_load_power",
            "temperature_entity": "sensor.weather_forecast_temperature",
        },
        "mqtt_host": "core-mosquitto",
        "mqtt_port": 1883,
    }

    monitor_active_period(config, ha_api, mqtt, state)

    assert mqtt.published
    topic, payload = mqtt.published[0]
    assert topic == "battery_api/text/schedule/set"
    assert payload["discharge"] == []


def test_generate_schedule_dry_run():
    logger.info("e2e: skips publish in dry-run mode")
    now = datetime.utcnow()
    price_curve = [
        {"start": now.isoformat(), "end": (now + timedelta(minutes=15)).isoformat(), "price": 0.10},
        {"start": (now + timedelta(minutes=15)).isoformat(), "end": (now + timedelta(minutes=30)).isoformat(), "price": 0.20},
    ]

    ha_api = DummyHaApi(
        {
            "sensor.energy_prices_price_import": {
                "state": "0.10",
                "attributes": {"price_curve": price_curve},
            }
            ,
            "sensor.energy_prices_price_export": {
                "state": "0.05",
                "attributes": {"price_curve": price_curve},
            }
        }
    )
    mqtt = DummyMqtt()

    config = {
        "heuristics": {"top_x_charge_hours": 1, "top_x_discharge_hours": 1, "excess_solar_threshold": 1000},
        "power": {"max_charge_power": 8000, "max_discharge_power": 8000, "min_discharge_power": 4000},
        "soc": {"min_soc": 5, "conservative_soc": 40, "target_eod_soc": 20},
        "temperature_based_discharge": {"enabled": False, "thresholds": []},
        "ev_charger": {"enabled": False, "charging_threshold": 500, "entity_id": "sensor.ev"},
        "timing": {"update_interval": 3600, "monitor_interval": 60},
        "dry_run": True,
        "entities": {
            "price_curve_entity": "sensor.energy_prices_price_import",
            "export_price_curve_entity": "sensor.energy_prices_price_export",
            "soc_entity": "sensor.battery_api_state_of_charge",
            "grid_power_entity": "sensor.grid_power",
            "solar_power_entity": "sensor.solar_power",
            "house_load_entity": "sensor.house_load_power",
            "temperature_entity": "sensor.weather_forecast_temperature",
        },
        "mqtt_host": "core-mosquitto",
        "mqtt_port": 1883,
    }

    schedule = generate_schedule(config, ha_api, mqtt)

    assert schedule["charge"]
    assert mqtt.published == []
