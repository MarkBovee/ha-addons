from app.main import OLD_ENTITIES


def test_active_legacy_entities_are_not_in_cleanup_list():
    active_entities = {
        "input_boolean.ca_charger_charging",
        "input_number.ca_charger_total_consumption_kwh",
        "input_number.ca_charger_current_power_w",
        "sensor.ca_charger_status",
        "sensor.ca_charger_power_kw",
        "sensor.ca_charger_voltage",
        "sensor.ca_charger_current",
        "binary_sensor.ca_charger_online",
        "binary_sensor.ca_charger_connector_enabled",
    }

    assert active_entities.isdisjoint(OLD_ENTITIES)
