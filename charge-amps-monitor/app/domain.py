"""Provider-neutral charger domain contracts.

These types are internal to the Charge Amps integration. Home Assistant is
the only boundary exposed to future HEMS consumers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, List, Optional, Protocol

from .models import ChargePoint, Connector


class ChargerState(str, Enum):
    OFFLINE = "offline"
    AVAILABLE = "available"
    PREPARING = "preparing"
    CHARGING = "charging"
    SUSPENDED = "suspended"
    FAULTED = "faulted"
    UNKNOWN = "unknown"


class CapabilityState(str, Enum):
    SUPPORTED = "supported"
    UNSUPPORTED = "unsupported"
    UNKNOWN = "unknown"


class CommandOutcome(str, Enum):
    SUCCESS = "success"
    UNSUPPORTED = "unsupported"
    INVALID = "invalid"
    CONSTRAINT_ERROR = "constraint_error"
    OFFLINE = "offline"
    FAULTED = "faulted"
    PROVIDER_ERROR = "provider_error"
    TIMEOUT = "timeout"


@dataclass(frozen=True)
class ChargerIdentity:
    charger_id: Optional[str]
    name: Optional[str]
    serial_number: Optional[str]
    manufacturer: str = "Charge Amps"
    model: Optional[str] = None


@dataclass(frozen=True)
class ChargerMeasurements:
    power_w: Optional[float] = None
    energy_kwh: Optional[float] = None
    current_a: Optional[float] = None
    voltage_v: Optional[float] = None


@dataclass(frozen=True)
class ChargerLimits:
    min_current_a: Optional[float] = None
    max_current_a: Optional[float] = None
    connector_min_current_a: Optional[float] = None
    connector_max_current_a: Optional[float] = None
    phase_count: Optional[int] = None


@dataclass(frozen=True)
class ChargerCapabilities:
    start: CapabilityState = CapabilityState.UNKNOWN
    stop: CapabilityState = CapabilityState.UNKNOWN
    current_control: CapabilityState = CapabilityState.UNKNOWN
    connector_enable: CapabilityState = CapabilityState.UNKNOWN
    scheduling: CapabilityState = CapabilityState.SUPPORTED
    limits: ChargerLimits = field(default_factory=ChargerLimits)
    reasons: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class Charger:
    identity: ChargerIdentity
    state: ChargerState
    online: Optional[bool]
    charging: Optional[bool]
    measurements: ChargerMeasurements
    limits: ChargerLimits
    capabilities: ChargerCapabilities
    raw_state: Optional[str] = None
    raw_diagnostics: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CommandResult:
    outcome: CommandOutcome
    command: str
    source: str
    requested_value: Optional[float] = None
    applied_value: Optional[float] = None
    error: Optional[str] = None

    @property
    def success(self) -> bool:
        return self.outcome is CommandOutcome.SUCCESS


@dataclass(frozen=True)
class ScheduleIntent:
    """Provider-neutral schedule intent owned by higher-level orchestration."""

    charge_point_id: str
    connector_id: int
    periods: list[dict[str, Any]]
    max_current_a: float
    timezone_name: str
    source: str


class ChargerPort(Protocol):
    """Internal integration port, never a HEMS interface."""

    def get_state(self) -> Charger:
        """Return normalized charger state."""

    def get_capabilities(self) -> ChargerCapabilities:
        """Return verified capability state."""

    def set_current(self, amps: float) -> CommandResult:
        """Request persistent current target."""

    def start(self) -> CommandResult:
        """Request immediate start."""

    def stop(self) -> CommandResult:
        """Request immediate stop."""


class SchedulePort(Protocol):
    """Internal schedule boundary used by standalone and legacy orchestration."""

    def upsert_schedule(self, **kwargs: Any) -> Optional[dict[str, Any]]:
        """Create or update a provider schedule."""

    def delete_schedule(self, charge_point_id: str, connector_id: int) -> bool:
        """Delete a provider schedule."""

    def get_schedules(self, charge_point_id: str) -> Optional[list[dict[str, Any]]]:
        """Read schedules for mutation verification."""


def normalize_state(charge_point: ChargePoint, connector: Connector) -> ChargerState:
    """Map provider state to a provider-neutral state."""
    if not charge_point.is_online:
        return ChargerState.OFFLINE
    if connector.error_code:
        return ChargerState.FAULTED
    if connector.is_charging:
        return ChargerState.CHARGING
    if connector.mode:
        normalized_mode = connector.mode.lower()
        if normalized_mode in {"preparing", "prepare"}:
            return ChargerState.PREPARING
        if normalized_mode in {"suspended", "suspend"}:
            return ChargerState.SUSPENDED
    return ChargerState.AVAILABLE


def charger_from_dtos(charge_point: ChargePoint, connector: Connector) -> Charger:
    """Convert current provider DTOs into normalized charger data."""
    def phase_values(prefix: str) -> list[float]:
        return [
            value
            for name, value in (
                (f"{prefix}1", getattr(connector, f"{prefix}1")),
                (f"{prefix}2", getattr(connector, f"{prefix}2")),
                (f"{prefix}3", getattr(connector, f"{prefix}3")),
            )
            if not connector.provided_fields or name in connector.provided_fields
        ]

    currents = phase_values("current")
    voltages = phase_values("voltage")
    has_energy = not connector.provided_fields or "totalConsumptionKwh" in connector.provided_fields

    measurements = ChargerMeasurements(
        power_w=(
            sum(voltage * current for voltage, current in zip(voltages, currents))
            if voltages and currents and len(voltages) == len(currents)
            else None
        ),
        energy_kwh=connector.total_consumption_kwh if has_energy else None,
        current_a=sum(currents) / len(currents) if currents else None,
        voltage_v=sum(voltages) / len(voltages) if voltages else None,
    )
    capabilities = ChargerCapabilities(
        start=CapabilityState.UNKNOWN,
        stop=CapabilityState.UNKNOWN,
        current_control=CapabilityState.UNKNOWN,
        connector_enable=CapabilityState.UNKNOWN,
        scheduling=CapabilityState.SUPPORTED,
        reasons={
            "start": "No verified Charge Amps start operation",
            "stop": "No verified Charge Amps stop operation",
            "current_control": "No verified Charge Amps current-control operation",
            "connector_enable": "No verified Charge Amps enable operation",
            "limits": "Provider limits are not verified",
        },
    )
    return Charger(
        identity=ChargerIdentity(
            charger_id=charge_point.id,
            name=charge_point.name,
            serial_number=charge_point.serial_number,
            model=charge_point.product_name or charge_point.product_type,
        ),
        state=normalize_state(charge_point, connector),
        online=charge_point.is_online,
        charging=connector.is_charging,
        measurements=measurements,
        limits=capabilities.limits,
        capabilities=capabilities,
        raw_state=charge_point.charge_point_status,
        raw_diagnostics={
            "connector_id": connector.connector_id,
            "connector_mode": connector.mode,
            "ocpp_status": connector.ocpp_status,
            "error_code": connector.error_code,
            "enabled": connector.enabled,
        },
    )


def unsupported_result(command: str, source: str, reason: str) -> CommandResult:
    """Build a truthful no-mutation result for an unverified operation."""
    return CommandResult(
        outcome=CommandOutcome.UNSUPPORTED,
        command=command,
        source=source,
        error=reason,
    )
