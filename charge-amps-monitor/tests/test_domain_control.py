from app.charge_amps_adapter import ChargeAmpsAdapter
from app.control_service import ChargerControlService
from app.domain import (
    CapabilityState,
    ChargerCapabilities,
    ChargerIdentity,
    ChargerLimits,
    ChargerMeasurements,
    ChargerState,
    CommandOutcome,
    Charger,
    charger_from_dtos,
)
from app.models import ChargePoint, Connector


class _Port:
    def __init__(self, charger):
        self.charger = charger
        self.calls = []

    def get_state(self):
        return self.charger

    def get_capabilities(self):
        return self.charger.capabilities

    def set_current(self, amps):
        self.calls.append(("set_current", amps))
        return None

    def start(self):
        self.calls.append(("start", None))
        return None

    def stop(self):
        self.calls.append(("stop", None))
        return None

    def upsert_schedule(self, **kwargs):
        self.calls.append(("upsert_schedule", kwargs))
        return {}

    def delete_schedule(self, charge_point_id, connector_id):
        self.calls.append(("delete_schedule", charge_point_id, connector_id))
        return True

    def get_schedules(self, charge_point_id):
        self.calls.append(("get_schedules", charge_point_id))
        return []


def _charger(capabilities):
    return Charger(
        identity=ChargerIdentity("id", "name", "serial"),
        state=ChargerState.AVAILABLE,
        online=True,
        charging=False,
        measurements=ChargerMeasurements(),
        limits=capabilities.limits,
        capabilities=capabilities,
    )


def test_provider_dto_mapping_preserves_measurements_and_unknown_controls():
    charge_point = ChargePoint(
        id="charger-1",
        name="Garage",
        serial_number="serial-1",
        charge_point_status="Online",
        connectors=[Connector(
            connector_id=1,
            is_charging=True,
            total_consumption_kwh=12.5,
            current1=4,
            voltage1=230,
        )],
    )

    charger = charger_from_dtos(charge_point, charge_point.connectors[0])

    assert charger.state is ChargerState.CHARGING
    assert charger.measurements.power_w == 920
    assert charger.measurements.energy_kwh == 12.5
    assert charger.capabilities.current_control is CapabilityState.UNKNOWN
    assert charger.limits.min_current_a is None


def test_unsupported_current_does_not_call_provider():
    capabilities = ChargerCapabilities(
        current_control=CapabilityState.UNKNOWN,
        reasons={"current_control": "provider operation not verified"},
    )
    port = _Port(_charger(capabilities))
    service = ChargerControlService(port)

    result = service.set_current(4, source="ha")

    assert result.outcome is CommandOutcome.UNSUPPORTED
    assert port.calls == []


def test_current_limits_reject_without_silent_clamp():
    capabilities = ChargerCapabilities(
        current_control=CapabilityState.SUPPORTED,
        limits=ChargerLimits(min_current_a=6, max_current_a=16, phase_count=1),
    )
    port = _Port(_charger(capabilities))
    service = ChargerControlService(port)

    result = service.set_current(4, source="ha")

    assert result.outcome is CommandOutcome.CONSTRAINT_ERROR
    assert result.requested_value == 4
    assert port.calls == []


def test_verified_command_without_provider_result_is_not_success():
    capabilities = ChargerCapabilities(
        start=CapabilityState.SUPPORTED,
        current_control=CapabilityState.SUPPORTED,
        limits=ChargerLimits(min_current_a=6, max_current_a=16, phase_count=1),
    )
    port = _Port(_charger(capabilities))
    service = ChargerControlService(port)

    result = service.start(source="ha")

    assert result.outcome is CommandOutcome.PROVIDER_ERROR


def test_current_control_rejects_offline_charger_before_provider_call():
    capabilities = ChargerCapabilities(
        current_control=CapabilityState.SUPPORTED,
        limits=ChargerLimits(min_current_a=6, max_current_a=16, phase_count=1),
    )
    charger = _charger(capabilities)
    charger = Charger(
        identity=charger.identity,
        state=ChargerState.OFFLINE,
        online=False,
        charging=False,
        measurements=charger.measurements,
        limits=charger.limits,
        capabilities=charger.capabilities,
    )
    port = _Port(charger)

    result = ChargerControlService(port).set_current(8, source="ha")

    assert result.outcome is CommandOutcome.OFFLINE
    assert port.calls == []


def test_current_control_rejects_faulted_or_disabled_charger():
    capabilities = ChargerCapabilities(
        current_control=CapabilityState.SUPPORTED,
        limits=ChargerLimits(min_current_a=6, max_current_a=16, phase_count=1),
    )
    base = _charger(capabilities)
    faulted = Charger(
        identity=base.identity,
        state=ChargerState.FAULTED,
        online=True,
        charging=False,
        measurements=base.measurements,
        limits=base.limits,
        capabilities=base.capabilities,
    )
    faulted.raw_diagnostics["enabled"] = True
    disabled = Charger(
        identity=base.identity,
        state=ChargerState.AVAILABLE,
        online=True,
        charging=False,
        measurements=base.measurements,
        limits=base.limits,
        capabilities=base.capabilities,
        raw_diagnostics={"enabled": False},
    )

    assert ChargerControlService(_Port(faulted)).set_current(8).outcome is CommandOutcome.FAULTED
    assert ChargerControlService(_Port(disabled)).set_current(8).outcome is CommandOutcome.CONSTRAINT_ERROR


def test_current_control_rejects_unknown_phase_count():
    capabilities = ChargerCapabilities(
        current_control=CapabilityState.SUPPORTED,
        limits=ChargerLimits(min_current_a=6, max_current_a=16),
    )

    result = ChargerControlService(_Port(_charger(capabilities))).set_current(8)

    assert result.outcome is CommandOutcome.UNSUPPORTED


def test_schedule_mutation_is_read_back_through_serialized_service():
    capabilities = ChargerCapabilities()
    port = _Port(_charger(capabilities))
    service = ChargerControlService(port, schedule_port=port)

    result = service.upsert_schedule(charge_point_id="charger-1", schedule_periods=[])

    assert result == {}
    assert [call[0] for call in port.calls] == ["upsert_schedule", "get_schedules"]


def test_unverified_adapter_commands_are_no_mutation_results():
    class _Api:
        pass

    adapter = ChargeAmpsAdapter(_Api())

    assert adapter.start().outcome is CommandOutcome.UNSUPPORTED
    assert adapter.stop().outcome is CommandOutcome.UNSUPPORTED
    assert adapter.set_current(4).outcome is CommandOutcome.UNSUPPORTED
