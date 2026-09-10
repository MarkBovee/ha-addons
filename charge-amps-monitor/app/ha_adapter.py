"""Home Assistant adapter for normalized Charge Amps state."""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

from .domain import CapabilityState, Charger

logger = logging.getLogger(__name__)
NORMALIZED_PREFIX = "charge_amps_monitor_"


class ChargerHaAdapter:
    """Publish additive normalized read-only entities.

    Writable entities are deliberately omitted until provider operations and
    limits are verified. Existing legacy publication remains untouched.
    """

    def __init__(self, mqtt_client: Any = None) -> None:
        self._mqtt = mqtt_client

    def publish_mqtt(self, charger: Charger, discovery: bool = False, error: Optional[str] = None) -> None:
        """Publish normalized state under the existing Charge Amps device."""
        if not self._mqtt:
            return
        if discovery:
            self._publish_discovery(charger, error)
        else:
            self._update_state(charger, error)

    def publish_rest(self, charger: Charger, publish_entity, error: Optional[str] = None) -> None:
        """Publish normalized state through the legacy REST fallback."""
        state_attrs = {
            "friendly_name": "Charger Status",
            "raw_state": charger.raw_state or "unknown",
        }
        publish_entity("sensor.charge_amps_monitor_state", charger.state.value, state_attrs)
        publish_entity(
            "binary_sensor.charge_amps_monitor_online",
            "on" if charger.online else "off",
            {"friendly_name": "Online", "device_class": "connectivity", "icon": "mdi:lan-connect"},
        )
        if charger.charging is not None:
            publish_entity(
                "binary_sensor.charge_amps_monitor_charging",
                "on" if charger.charging else "off",
                {"friendly_name": "Charging", "device_class": "charging", "icon": "mdi:ev-station"},
            )
        self._publish_rest_measurement(
            publish_entity, "power", charger.measurements.power_w, "W", "power"
        )
        self._publish_rest_measurement(
            publish_entity, "energy", charger.measurements.energy_kwh, "kWh", "energy"
        )
        self._publish_rest_measurement(
            publish_entity, "current", charger.measurements.current_a, "A", "current"
        )
        self._publish_rest_measurement(
            publish_entity, "voltage", charger.measurements.voltage_v, "V", "voltage"
        )
        publish_entity(
            "sensor.charge_amps_monitor_capabilities",
            self._capability_state(charger),
            {
                "friendly_name": "Capabilities",
                "entity_category": "diagnostic",
                "icon": "mdi:format-list-bulleted",
                **self._capability_attributes(charger),
            },
        )
        publish_entity(
            "sensor.charge_amps_monitor_error",
            error or "none",
            {"friendly_name": "Error", "entity_category": "diagnostic", "icon": "mdi:alert-circle"},
        )

    def publish_unavailable(self, publish_entity=None, error: str = "provider_unavailable") -> None:
        """Mark normalized entities unavailable after a failed provider refresh."""
        if publish_entity:
            publish_entity(
                "sensor.charge_amps_monitor_state",
                "unavailable",
                {"friendly_name": "Charger Status"},
            )
            publish_entity(
                "binary_sensor.charge_amps_monitor_online",
                "unavailable",
                {"friendly_name": "Online", "device_class": "connectivity", "icon": "mdi:lan-connect"},
            )
            publish_entity(
                "binary_sensor.charge_amps_monitor_charging",
                "unavailable",
                {"friendly_name": "Charging", "device_class": "charging", "icon": "mdi:ev-station"},
            )
            for name, unit, device_class in (
                ("power", "W", "power"),
                ("energy", "kWh", "energy"),
                ("current", "A", "current"),
                ("voltage", "V", "voltage"),
            ):
                publish_entity(
                    f"sensor.charge_amps_monitor_{name}",
                    "unavailable",
                    {
                        "friendly_name": {
                            "power": "Charging Power",
                            "energy": "Charging Energy",
                            "current": "Charging Current",
                            "voltage": "Charging Voltage",
                        }[name],
                        "unit_of_measurement": unit,
                        "device_class": device_class,
                    },
                )
            publish_entity(
                "sensor.charge_amps_monitor_error",
                error,
                {"friendly_name": "Error", "entity_category": "diagnostic", "icon": "mdi:alert-circle"},
            )
            return

        if not self._mqtt:
            return
        for component, object_id, state in (
            ("sensor", f"{NORMALIZED_PREFIX}state", "unavailable"),
            ("binary_sensor", f"{NORMALIZED_PREFIX}online", "unavailable"),
            ("binary_sensor", f"{NORMALIZED_PREFIX}charging", "unavailable"),
            ("sensor", f"{NORMALIZED_PREFIX}power", "unavailable"),
            ("sensor", f"{NORMALIZED_PREFIX}energy", "unavailable"),
            ("sensor", f"{NORMALIZED_PREFIX}current", "unavailable"),
            ("sensor", f"{NORMALIZED_PREFIX}voltage", "unavailable"),
            ("sensor", f"{NORMALIZED_PREFIX}error", error),
        ):
            self._mqtt.update_state(component, object_id, state)

    def _publish_discovery(self, charger: Charger, error: Optional[str]) -> None:
        from shared.ha_mqtt_discovery import EntityConfig

        for component, object_id in self._legacy_normalized_entities():
            self._mqtt.remove_entity(component, object_id)

        self._mqtt.publish_sensor(EntityConfig(
            object_id=f"{NORMALIZED_PREFIX}state",
            name="Charger Status",
            state=charger.state.value,
            attributes={"raw_state": charger.raw_state or "unknown"},
        ))

        self._mqtt.publish_binary_sensor(EntityConfig(
            object_id=f"{NORMALIZED_PREFIX}online",
            name="Online",
            state="unavailable" if charger.online is None else "ON" if charger.online else "OFF",
            device_class="connectivity",
        ))
        self._mqtt.publish_binary_sensor(EntityConfig(
            object_id=f"{NORMALIZED_PREFIX}charging",
            name="Charging",
            state="unavailable" if charger.charging is None else "ON" if charger.charging else "OFF",
            device_class="charging",
        ))
        self._publish_discovery_measurement(f"{NORMALIZED_PREFIX}power", "Charging Power", charger.measurements.power_w, "W", "power", icon="mdi:flash")
        self._publish_discovery_measurement(f"{NORMALIZED_PREFIX}energy", "Charging Energy", charger.measurements.energy_kwh, "kWh", "energy", "total_increasing", icon="mdi:lightning-bolt")
        self._publish_discovery_measurement(f"{NORMALIZED_PREFIX}current", "Charging Current", charger.measurements.current_a, "A", "current", icon="mdi:current-ac")
        self._publish_discovery_measurement(f"{NORMALIZED_PREFIX}voltage", "Charging Voltage", charger.measurements.voltage_v, "V", "voltage", icon="mdi:lightning-bolt")
        self._mqtt.publish_sensor(EntityConfig(
            object_id=f"{NORMALIZED_PREFIX}capabilities",
            name="Capabilities",
            state=self._capability_state(charger),
            entity_category="diagnostic",
            icon="mdi:format-list-bulleted",
            attributes=self._capability_attributes(charger),
        ))
        self._mqtt.publish_sensor(EntityConfig(
            object_id=f"{NORMALIZED_PREFIX}error",
            name="Error",
            state=error or "none",
            entity_category="diagnostic",
            icon="mdi:alert-circle",
        ))

    @staticmethod
    def _legacy_normalized_entities() -> tuple[tuple[str, str], ...]:
        """Return malformed normalized discovery IDs from pre-release builds."""
        entity_suffixes = (
            ("sensor", "state"),
            ("binary_sensor", "online"),
            ("binary_sensor", "charging"),
            ("sensor", "power"),
            ("sensor", "energy"),
            ("sensor", "current"),
            ("sensor", "voltage"),
            ("sensor", "capabilities"),
            ("sensor", "error"),
        )
        prefixes = ("monitor_", NORMALIZED_PREFIX, NORMALIZED_PREFIX * 2)
        return tuple(
            (component, f"{prefix}{suffix}")
            for component, suffix in entity_suffixes
            for prefix in prefixes
        )

    def _update_state(self, charger: Charger, error: Optional[str]) -> None:
        self._mqtt.update_state("sensor", f"{NORMALIZED_PREFIX}state", charger.state.value)
        self._mqtt.update_state(
            "binary_sensor",
            f"{NORMALIZED_PREFIX}online",
            "unavailable" if charger.online is None else "ON" if charger.online else "OFF",
        )
        if charger.charging is not None:
            self._mqtt.update_state("binary_sensor", f"{NORMALIZED_PREFIX}charging", "ON" if charger.charging else "OFF")
        self._update_measurement(f"{NORMALIZED_PREFIX}power", charger.measurements.power_w)
        self._update_measurement(f"{NORMALIZED_PREFIX}energy", charger.measurements.energy_kwh)
        self._update_measurement(f"{NORMALIZED_PREFIX}current", charger.measurements.current_a)
        self._update_measurement(f"{NORMALIZED_PREFIX}voltage", charger.measurements.voltage_v)
        self._mqtt.update_state(
            "sensor",
            f"{NORMALIZED_PREFIX}capabilities",
            self._capability_state(charger),
            self._capability_attributes(charger),
        )
        self._mqtt.update_state("sensor", f"{NORMALIZED_PREFIX}error", error or "none")

    def _publish_discovery_measurement(
        self,
        object_id: str,
        name: str,
        value: Optional[float],
        unit: str,
        device_class: str,
        state_class: str = "measurement",
        icon: Optional[str] = None,
    ) -> None:
        from shared.ha_mqtt_discovery import EntityConfig

        self._mqtt.publish_sensor(EntityConfig(
            object_id=object_id,
            name=name,
            state="unavailable" if value is None else str(value),
            unit_of_measurement=unit,
            device_class=device_class,
            state_class=state_class,
            icon=icon,
        ))

    def _update_measurement(self, object_id: str, value: Optional[float]) -> None:
        self._mqtt.update_state("sensor", object_id, "unavailable" if value is None else str(value))

    @staticmethod
    def _publish_rest_measurement(publish_entity, name: str, value: Optional[float], unit: str, device_class: str) -> None:
        publish_entity(
            f"sensor.charge_amps_monitor_{name}",
            "unavailable" if value is None else str(value),
            {
                "friendly_name": {
                    "power": "Charging Power",
                    "energy": "Charging Energy",
                    "current": "Charging Current",
                    "voltage": "Charging Voltage",
                }[name],
                "unit_of_measurement": unit,
                "device_class": device_class,
            },
        )

    @staticmethod
    def _capability_state(charger: Charger) -> str:
        capabilities = charger.capabilities
        if all(value is CapabilityState.SUPPORTED for value in (
            capabilities.start,
            capabilities.stop,
            capabilities.current_control,
            capabilities.connector_enable,
        )):
            return "full"
        return "read_only"

    @staticmethod
    def _capability_attributes(charger: Charger) -> dict[str, Any]:
        capabilities = charger.capabilities
        return {
            "start": capabilities.start.value,
            "stop": capabilities.stop.value,
            "current_control": capabilities.current_control.value,
            "connector_enable": capabilities.connector_enable.value,
            "scheduling": capabilities.scheduling.value,
            "reasons": json.dumps(capabilities.reasons, sort_keys=True),
        }
