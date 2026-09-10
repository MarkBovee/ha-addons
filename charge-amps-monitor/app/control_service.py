"""Internal serialized charger control and schedule service."""

from __future__ import annotations

import threading
from typing import Any, Callable, Optional

from .domain import (
    CapabilityState,
    Charger,
    ChargerCapabilities,
    ChargerPort,
    CommandOutcome,
    CommandResult,
    SchedulePort,
    unsupported_result,
)


class ChargerControlService:
    """Single internal mutation path for adapter and compatibility code."""

    def __init__(
        self,
        port: ChargerPort,
        schedule_port: Optional[SchedulePort] = None,
        state_provider: Optional[Callable[[], Charger]] = None,
    ) -> None:
        self._port = port
        self._schedule_port = schedule_port
        self._state_provider = state_provider or port.get_state
        self._lock = threading.RLock()
        self._last_result: Optional[CommandResult] = None

    @property
    def last_result(self) -> Optional[CommandResult]:
        return self._last_result

    def get_state(self) -> Charger:
        return self._state_provider()

    def get_capabilities(self) -> ChargerCapabilities:
        return self._port.get_capabilities()

    def set_current(self, amps: float, source: str = "internal") -> CommandResult:
        with self._lock:
            result = self._validate_current(amps, source)
            if result is None:
                result = self._port.set_current(amps)
            if result is None:
                result = CommandResult(
                    outcome=CommandOutcome.PROVIDER_ERROR,
                    command="set_current",
                    source=source,
                    requested_value=float(amps),
                    error="Provider did not return a command result",
                )
            elif result.success:
                result = self._refresh_result(result)
            self._last_result = result
            return result

    def start(self, source: str = "internal") -> CommandResult:
        with self._lock:
            result = self._check_capability("start", source)
            if result is None:
                result = self._port.start()
            if result is None:
                result = CommandResult(
                    outcome=CommandOutcome.PROVIDER_ERROR,
                    command="start",
                    source=source,
                    error="Provider did not return a command result",
                )
            elif result.success:
                result = self._refresh_result(result)
            self._last_result = result
            return result

    def stop(self, source: str = "internal") -> CommandResult:
        with self._lock:
            result = self._check_capability("stop", source)
            if result is None:
                result = self._port.stop()
            if result is None:
                result = CommandResult(
                    outcome=CommandOutcome.PROVIDER_ERROR,
                    command="stop",
                    source=source,
                    error="Provider did not return a command result",
                )
            elif result.success:
                result = self._refresh_result(result)
            self._last_result = result
            return result

    def upsert_schedule(self, source: str = "internal", **kwargs: Any) -> Optional[dict[str, Any]]:
        if not self._schedule_port:
            return None
        with self._lock:
            result = self._schedule_port.upsert_schedule(**kwargs)
            if result is None:
                return None
            charge_point_id = kwargs.get("charge_point_id")
            if charge_point_id and self._schedule_port.get_schedules(charge_point_id) is None:
                return None
            return result

    def delete_schedule(self, charge_point_id: str, connector_id: int, source: str = "internal") -> bool:
        if not self._schedule_port:
            return False
        with self._lock:
            return self._schedule_port.delete_schedule(charge_point_id, connector_id)

    def verify_schedule(self, charge_point_id: str, source: str = "internal") -> Optional[list[dict[str, Any]]]:
        """Read back provider schedule while holding mutation serialization lock."""
        if not self._schedule_port:
            return None
        with self._lock:
            return self._schedule_port.get_schedules(charge_point_id)

    def get_schedules(self, charge_point_id: str) -> Optional[list[dict[str, Any]]]:
        """Read schedules through the serialized internal schedule boundary."""
        return self.verify_schedule(charge_point_id)

    def _check_capability(self, name: str, source: str) -> Optional[CommandResult]:
        capabilities = self.get_capabilities()
        capability = getattr(capabilities, name)
        if capability is not CapabilityState.SUPPORTED:
            reason = capabilities.reasons.get(name, f"{name} is not verified")
            return unsupported_result(name, source, reason)
        return None

    def _refresh_result(self, result: CommandResult) -> CommandResult:
        """Require a normalized state refresh after a provider mutation."""
        try:
            self._state_provider()
            return result
        except Exception as exc:
            return CommandResult(
                outcome=CommandOutcome.PROVIDER_ERROR,
                command=result.command,
                source=result.source,
                requested_value=result.requested_value,
                applied_value=None,
                error=f"Command succeeded but state refresh failed: {exc}",
            )

    def _validate_current(self, amps: float, source: str) -> Optional[CommandResult]:
        capabilities = self.get_capabilities()
        if capabilities.current_control is not CapabilityState.SUPPORTED:
            return unsupported_result(
                "set_current",
                source,
                capabilities.reasons.get("current_control", "current control is not verified"),
            )

        state = self.get_state()
        if state.online is not True:
            return CommandResult(
                outcome=CommandOutcome.OFFLINE,
                command="set_current",
                source=source,
                error="Charger is not online",
            )
        if state.state.value == "faulted":
            return CommandResult(
                outcome=CommandOutcome.FAULTED,
                command="set_current",
                source=source,
                error="Charger is faulted",
            )
        if state.raw_diagnostics.get("enabled") is False:
            return CommandResult(
                outcome=CommandOutcome.CONSTRAINT_ERROR,
                command="set_current",
                source=source,
                error="Charger connector is disabled",
            )

        try:
            value = float(amps)
        except (TypeError, ValueError):
            return CommandResult(
                outcome=CommandOutcome.INVALID,
                command="set_current",
                source=source,
                error="Current must be numeric",
            )

        limits = capabilities.limits
        minimum = limits.connector_min_current_a or limits.min_current_a
        maximum = limits.connector_max_current_a or limits.max_current_a
        if limits.phase_count is None:
            return unsupported_result(
                "set_current",
                source,
                "Phase count is not verified",
            )
        if limits.phase_count <= 0:
            return CommandResult(
                outcome=CommandOutcome.CONSTRAINT_ERROR,
                command="set_current",
                source=source,
                error="Phase count must be greater than zero",
            )
        if minimum is None or maximum is None:
            return unsupported_result(
                "set_current",
                source,
                "Current limits are not verified",
            )
        if value <= 0:
            return CommandResult(
                outcome=CommandOutcome.INVALID,
                command="set_current",
                source=source,
                requested_value=value,
                error="Current must be greater than zero",
            )
        if value < minimum or value > maximum:
            return CommandResult(
                outcome=CommandOutcome.CONSTRAINT_ERROR,
                command="set_current",
                source=source,
                requested_value=value,
                error=f"Current must be between {minimum} A and {maximum} A",
            )
        return None
