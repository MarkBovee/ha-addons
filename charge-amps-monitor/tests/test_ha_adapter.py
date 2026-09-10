from app.domain import (
    CapabilityState,
    Charger,
    ChargerCapabilities,
    ChargerIdentity,
    ChargerLimits,
    ChargerMeasurements,
    ChargerState,
)
from app.ha_adapter import ChargerHaAdapter


class _Mqtt:
    def __init__(self):
        self.discovery = []
        self.states = []
        self.removed = []

    def publish_sensor(self, config):
        self.discovery.append(("sensor", config.object_id, config.state, config.name))

    def publish_binary_sensor(self, config):
        self.discovery.append(("binary_sensor", config.object_id, config.state, config.name))

    def update_state(self, component, object_id, state, attributes=None):
        self.states.append((component, object_id, state, attributes))

    def remove_entity(self, component, object_id):
        self.removed.append((component, object_id))
        return True


def _charger():
    capabilities = ChargerCapabilities(
        start=CapabilityState.UNKNOWN,
        stop=CapabilityState.UNKNOWN,
        current_control=CapabilityState.UNKNOWN,
        connector_enable=CapabilityState.UNKNOWN,
        limits=ChargerLimits(),
    )
    return Charger(
        identity=ChargerIdentity("charger-1", "Garage", "serial-1"),
        state=ChargerState.AVAILABLE,
        online=True,
        charging=False,
        measurements=ChargerMeasurements(power_w=0, energy_kwh=2, current_a=0, voltage_v=230),
        limits=capabilities.limits,
        capabilities=capabilities,
    )


def test_normalized_mqtt_entities_are_additive_and_read_only():
    mqtt = _Mqtt()
    ChargerHaAdapter(mqtt).publish_mqtt(_charger(), discovery=True)

    ids = {object_id for _, object_id, _, _ in mqtt.discovery}
    assert {
        "monitor_state",
        "monitor_online",
        "monitor_charging",
        "monitor_power",
        "monitor_energy",
    } <= ids
    assert not any(
        object_id in {"current", "start", "stop", "enabled"}
        for _, object_id, _, _ in mqtt.discovery
    )

    names = {object_id: name for _, object_id, _, name in mqtt.discovery}
    assert names["monitor_state"] == "Charger Status"
    assert names["monitor_power"] == "Charging Power"
    assert all("Charge Amps Monitor Charge Amps Monitor" not in name for name in names.values())
    charging_config = next(item for item in mqtt.discovery if item[1] == "monitor_charging")
    assert charging_config[0] == "binary_sensor"
    assert ("sensor", "monitor_state") in mqtt.removed
    assert ("sensor", "charge_amps_monitor_state") in mqtt.removed


def test_normalized_rest_entities_use_monitor_prefix():
    published = []
    ChargerHaAdapter().publish_rest(
        _charger(),
        lambda entity_id, state, attributes: published.append((entity_id, state, attributes)),
    )

    entity_ids = {entity_id for entity_id, _, _ in published}
    assert "sensor.charge_amps_monitor_state" in entity_ids
    assert "sensor.charge_amps_monitor_power" in entity_ids
    assert "sensor.charge_amps_monitor_energy" in entity_ids
    assert "number.charge_amps_monitor_current" not in entity_ids


def test_missing_measurement_is_published_unavailable():
    charger = _charger()
    charger = Charger(
        identity=charger.identity,
        state=charger.state,
        online=charger.online,
        charging=charger.charging,
        measurements=ChargerMeasurements(),
        limits=charger.limits,
        capabilities=charger.capabilities,
    )
    published = []

    ChargerHaAdapter().publish_rest(
        charger,
        lambda entity_id, state, attributes: published.append((entity_id, state)),
    )

    states = dict(published)
    assert states["sensor.charge_amps_monitor_power"] == "unavailable"

    mqtt = _Mqtt()
    ChargerHaAdapter(mqtt).publish_mqtt(charger, discovery=True)

    discovery_states = {object_id: state for _, object_id, state, _ in mqtt.discovery}
    assert discovery_states["monitor_power"] == "unavailable"


def test_normalized_measurements_publish_provider_values():
    charger = _charger()
    charger = Charger(
        identity=charger.identity,
        state=charger.state,
        online=charger.online,
        charging=charger.charging,
        measurements=ChargerMeasurements(
            power_w=0.0,
            energy_kwh=0.0,
            current_a=11.6,
            voltage_v=228.1,
        ),
        limits=charger.limits,
        capabilities=charger.capabilities,
    )
    mqtt = _Mqtt()

    ChargerHaAdapter(mqtt).publish_mqtt(charger, discovery=True)

    states = {object_id: state for _, object_id, state, _ in mqtt.discovery}
    assert states["monitor_current"] == "11.6"
    assert states["monitor_voltage"] == "228.1"
    assert states["monitor_power"] == "0.0"
    assert states["monitor_energy"] == "0.0"


def test_normalized_discovery_preserves_unique_id_contracts():
    from shared.ha_mqtt_discovery import MqttDiscovery

    discovery = MqttDiscovery.__new__(MqttDiscovery)
    discovery.addon_id = "charge_amps"
    discovery.addon_name = "Charge Amps Monitor"
    discovery.manufacturer = "Charge Amps"
    discovery.model = "EV Charger"

    assert discovery._unique_id("charging") == "charge_amps_charging"
    assert discovery._unique_id("current_power") == "charge_amps_current_power"
    assert discovery._unique_id("charge_amps_monitor_state") == "charge_amps_monitor_state"
    assert discovery._object_id_with_prefix("charge_amps_monitor_state") == "charge_amps_monitor_state"
    assert discovery.device_info == {
        "identifiers": ["charge_amps"],
        "name": "Charge Amps Monitor",
        "manufacturer": "Charge Amps",
        "model": "EV Charger",
    }
