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

    def publish_sensor(self, config):
        self.discovery.append(("sensor", config.object_id, config.state))

    def publish_binary_sensor(self, config):
        self.discovery.append(("binary_sensor", config.object_id, config.state))

    def update_state(self, component, object_id, state, attributes=None):
        self.states.append((component, object_id, state, attributes))


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

    ids = {object_id for _, object_id, _ in mqtt.discovery}
    assert {"monitor_state", "monitor_online", "monitor_charging", "monitor_power", "monitor_energy"} <= ids
    assert not any(object_id in {"current", "start", "stop", "enabled"} for _, object_id, _ in mqtt.discovery)


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
