"""Charge Amps infrastructure-to-domain adapter."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from .charger_api import ChargerApi
from .domain import (
    CapabilityState,
    Charger,
    ChargerCapabilities,
    ChargerPort,
    CommandResult,
    SchedulePort,
    charger_from_dtos,
    unsupported_result,
)


class ChargeAmpsAdapter(ChargerPort, SchedulePort):
    """Map verified Charge Amps API operations to internal contracts."""

    def __init__(self, api: ChargerApi, connector_id: int = 1) -> None:
        self.api = api
        self.connector_id = connector_id
        self._last_state: Optional[Charger] = None

    def get_state(self) -> Charger:
        """Read and normalize first configured charge point and connector."""
        charge_points = self.api.get_charge_points()
        if not charge_points or not charge_points[0].connectors:
            raise RuntimeError("No Charge Amps charger connector available")
        charge_point = charge_points[0]
        connector = next(
            (item for item in charge_point.connectors if item.connector_id == self.connector_id),
            charge_point.connectors[0],
        )
        self._last_state = charger_from_dtos(charge_point, connector)
        return self._last_state

    def get_capabilities(self) -> ChargerCapabilities:
        """Return only capabilities supported by verified provider operations."""
        if self._last_state:
            return self._last_state.capabilities
        return ChargerCapabilities(
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

    def set_current(self, amps: float) -> CommandResult:
        return unsupported_result(
            "set_current",
            "integration",
            "Charge Amps current-control operation is not verified",
        )

    def start(self) -> CommandResult:
        return unsupported_result(
            "start",
            "integration",
            "Charge Amps start operation is not verified",
        )

    def stop(self) -> CommandResult:
        return unsupported_result(
            "stop",
            "integration",
            "Charge Amps stop operation is not verified",
        )

    def upsert_schedule(self, **kwargs: Any) -> Optional[dict[str, Any]]:
        """Execute verified schedule upsert operation."""
        return self.api.upsert_schedule(**kwargs)

    def delete_schedule(self, charge_point_id: str, connector_id: int) -> bool:
        """Execute verified schedule delete operation."""
        return self.api.delete_schedule(charge_point_id, connector_id)

    def get_schedules(self, charge_point_id: str) -> Optional[list[dict[str, Any]]]:
        """Read schedules for optional read-back verification."""
        return self.api.get_schedules(charge_point_id)
