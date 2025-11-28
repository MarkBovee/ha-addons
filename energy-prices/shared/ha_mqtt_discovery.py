"""Home Assistant MQTT Discovery helper module.

This module provides MQTT-based entity creation with proper unique_id support,
allowing entities to be managed from the Home Assistant UI.

Usage:
    from shared.ha_mqtt_discovery import MqttDiscovery, EntityConfig
    
    mqtt = MqttDiscovery(
        addon_name="energy-prices",
        addon_id="energy_prices",
        mqtt_host="core-mosquitto",  # or localhost for local dev
        mqtt_port=1883
    )
    
    if mqtt.connect():
        mqtt.publish_sensor(EntityConfig(
            object_id="price_import",
            name="Electricity Import Price",
            state="12.34",
            unit_of_measurement="cents/kWh",
            device_class="monetary",
            icon="mdi:currency-eur",
            attributes={"price_curve": [...]}
        ))
        mqtt.disconnect()
"""

import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Try to import paho-mqtt, provide helpful error if missing
try:
    import paho.mqtt.client as mqtt
    MQTT_AVAILABLE = True
except ImportError:
    MQTT_AVAILABLE = False
    logger.warning("paho-mqtt not installed. MQTT Discovery will not be available.")


@dataclass
class EntityConfig:
    """Configuration for a Home Assistant entity.
    
    Attributes:
        object_id: Unique object ID within the addon (e.g., "price_import")
        name: Human-readable name (e.g., "Electricity Import Price")
        state: Current state value as string
        unit_of_measurement: Unit (e.g., "cents/kWh", "W", "V")
        device_class: HA device class (e.g., "monetary", "power", "voltage")
        state_class: State class for statistics (e.g., "measurement", "total_increasing")
        icon: MDI icon (e.g., "mdi:currency-eur")
        entity_category: Entity category ("config", "diagnostic", or None)
        attributes: Additional attributes to include in state
        enabled_by_default: Whether entity is enabled by default
    """
    object_id: str
    name: str
    state: str
    unit_of_measurement: Optional[str] = None
    device_class: Optional[str] = None
    state_class: Optional[str] = None
    icon: Optional[str] = None
    entity_category: Optional[str] = None
    attributes: Dict[str, Any] = field(default_factory=dict)
    enabled_by_default: bool = True


@dataclass
class NumberConfig:
    """Configuration for a Home Assistant number entity.
    
    Attributes:
        object_id: Unique object ID within the addon
        name: Human-readable name
        min_value: Minimum value
        max_value: Maximum value
        step: Step increment
        state: Current value as string
        unit_of_measurement: Unit (e.g., "W", "min")
        device_class: HA device class (e.g., "power")
        mode: Display mode ("auto", "box", "slider")
        icon: MDI icon
        entity_category: Entity category ("config", "diagnostic", or None)
    """
    object_id: str
    name: str
    min_value: float
    max_value: float
    step: float = 1.0
    state: str = "0"
    unit_of_measurement: Optional[str] = None
    device_class: Optional[str] = None
    mode: str = "auto"
    icon: Optional[str] = None
    entity_category: Optional[str] = None


@dataclass
class SelectConfig:
    """Configuration for a Home Assistant select entity.
    
    Attributes:
        object_id: Unique object ID within the addon
        name: Human-readable name
        options: List of selectable options
        state: Currently selected option
        icon: MDI icon
        entity_category: Entity category ("config", "diagnostic", or None)
    """
    object_id: str
    name: str
    options: List[str]
    state: str
    icon: Optional[str] = None
    entity_category: Optional[str] = None


@dataclass
class ButtonConfig:
    """Configuration for a Home Assistant button entity.
    
    Attributes:
        object_id: Unique object ID within the addon
        name: Human-readable name
        device_class: HA device class (e.g., "restart", "update")
        icon: MDI icon
        entity_category: Entity category ("config", "diagnostic", or None)
    """
    object_id: str
    name: str
    device_class: Optional[str] = None
    icon: Optional[str] = None
    entity_category: Optional[str] = None


@dataclass 
class TextConfig:
    """Configuration for a Home Assistant text entity.
    
    Attributes:
        object_id: Unique object ID within the addon
        name: Human-readable name
        state: Current text value
        min_length: Minimum text length (default: 0)
        max_length: Maximum text length (default: 255)
        pattern: Regex pattern for validation
        mode: Text mode ("text" or "password")
        icon: MDI icon
        entity_category: Entity category ("config", "diagnostic", or None)
    """
    object_id: str
    name: str
    state: str = ""
    min_length: int = 0
    max_length: int = 255
    pattern: Optional[str] = None
    mode: str = "text"
    icon: Optional[str] = None
    entity_category: Optional[str] = None


class MqttDiscovery:
    """MQTT Discovery client for Home Assistant.
    
    Creates entities with proper unique_id support via MQTT Discovery protocol.
    Entities are grouped under a device in the HA UI.
    """
    
    DISCOVERY_PREFIX = "homeassistant"
    
    def __init__(
        self,
        addon_name: str,
        addon_id: str,
        mqtt_host: str = "core-mosquitto",
        mqtt_port: int = 1883,
        mqtt_user: Optional[str] = None,
        mqtt_password: Optional[str] = None,
        manufacturer: str = "HA Addons",
        model: Optional[str] = None,
    ):
        """Initialize MQTT Discovery client.
        
        Args:
            addon_name: Human-readable addon name (e.g., "Energy Prices")
            addon_id: Machine-friendly addon ID (e.g., "energy_prices")
            mqtt_host: MQTT broker hostname (default: core-mosquitto for HA)
            mqtt_port: MQTT broker port (default: 1883)
            mqtt_user: MQTT username (optional)
            mqtt_password: MQTT password (optional)
            manufacturer: Device manufacturer shown in HA
            model: Device model shown in HA (defaults to addon_name)
        """
        if not MQTT_AVAILABLE:
            raise ImportError(
                "paho-mqtt is required for MQTT Discovery. "
                "Install with: pip install paho-mqtt"
            )
        
        self.addon_name = addon_name
        self.addon_id = addon_id
        self.mqtt_host = mqtt_host
        self.mqtt_port = mqtt_port
        self.mqtt_user = mqtt_user
        self.mqtt_password = mqtt_password
        self.manufacturer = manufacturer
        self.model = model or addon_name
        
        self._client: Optional[mqtt.Client] = None
        self._connected = False
        self._published_entities: List[str] = []
    
    @property
    def device_info(self) -> Dict[str, Any]:
        """Get device info for MQTT Discovery payloads."""
        return {
            "identifiers": [self.addon_id],
            "name": self.addon_name,
            "manufacturer": self.manufacturer,
            "model": self.model,
        }
    
    def _unique_id(self, object_id: str) -> str:
        """Generate unique ID for an entity."""
        return f"{self.addon_id}_{object_id}"
    
    def _state_topic(self, component: str, object_id: str) -> str:
        """Get state topic for an entity."""
        return f"{self.addon_id}/{component}/{object_id}/state"
    
    def _attributes_topic(self, component: str, object_id: str) -> str:
        """Get JSON attributes topic for an entity."""
        return f"{self.addon_id}/{component}/{object_id}/attributes"
    
    def _discovery_topic(self, component: str, object_id: str) -> str:
        """Get discovery config topic for an entity."""
        return f"{self.DISCOVERY_PREFIX}/{component}/{self.addon_id}/{object_id}/config"
    
    def _on_connect(self, client, userdata, flags, reason_code, properties=None):
        """Callback when MQTT connection is established.
        
        Note: paho-mqtt 2.x uses ReasonCode objects instead of int return codes.
        """
        # paho-mqtt 2.x: reason_code is a ReasonCode object
        # Success is when reason_code == 0 or reason_code.is_failure is False
        if reason_code == 0 or (hasattr(reason_code, 'is_failure') and not reason_code.is_failure):
            logger.info("Connected to MQTT broker at %s:%d", self.mqtt_host, self.mqtt_port)
            self._connected = True
        else:
            logger.error("Failed to connect to MQTT broker: %s", reason_code)
            self._connected = False
    
    def _on_disconnect(self, client, userdata, disconnect_flags, reason_code, properties=None):
        """Callback when MQTT connection is lost.
        
        Note: paho-mqtt 2.x callback has different signature with disconnect_flags.
        """
        logger.info("Disconnected from MQTT broker: %s", reason_code)
        self._connected = False
    
    def connect(self, timeout: float = 10.0) -> bool:
        """Connect to MQTT broker.
        
        Args:
            timeout: Connection timeout in seconds
            
        Returns:
            True if connected successfully, False otherwise
        """
        try:
            # Use callback API version 2 for paho-mqtt 2.x compatibility
            self._client = mqtt.Client(
                callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
                client_id=f"{self.addon_id}_discovery",
                protocol=mqtt.MQTTv311,
            )
            
            self._client.on_connect = self._on_connect
            self._client.on_disconnect = self._on_disconnect
            
            if self.mqtt_user and self.mqtt_password:
                self._client.username_pw_set(self.mqtt_user, self.mqtt_password)
            
            logger.info("Connecting to MQTT broker at %s:%d...", self.mqtt_host, self.mqtt_port)
            self._client.connect(self.mqtt_host, self.mqtt_port, keepalive=60)
            self._client.loop_start()
            
            # Wait for connection with timeout
            start = time.time()
            while not self._connected and (time.time() - start) < timeout:
                time.sleep(0.1)
            
            if not self._connected:
                logger.error("MQTT connection timeout after %.1f seconds", timeout)
                self._client.loop_stop()
                return False
            
            return True
            
        except Exception as e:
            logger.error("Failed to connect to MQTT broker: %s", e)
            return False
    
    def disconnect(self):
        """Disconnect from MQTT broker."""
        if self._client:
            self._client.loop_stop()
            self._client.disconnect()
            self._client = None
            self._connected = False
            logger.info("Disconnected from MQTT broker")
    
    def is_connected(self) -> bool:
        """Check if connected to MQTT broker."""
        return self._connected and self._client is not None
    
    def _publish(self, topic: str, payload: Any, retain: bool = True) -> bool:
        """Publish a message to MQTT.
        
        Args:
            topic: MQTT topic
            payload: Message payload (will be JSON-encoded if dict/list)
            retain: Whether to retain the message
            
        Returns:
            True if published successfully
        """
        if not self.is_connected():
            logger.error("Cannot publish: not connected to MQTT broker")
            return False
        
        try:
            if isinstance(payload, (dict, list)):
                payload = json.dumps(payload)
            elif not isinstance(payload, str):
                payload = str(payload)
            
            result = self._client.publish(topic, payload, retain=retain, qos=1)
            result.wait_for_publish(timeout=5.0)
            
            if result.rc != mqtt.MQTT_ERR_SUCCESS:
                logger.error("Failed to publish to %s: rc=%d", topic, result.rc)
                return False
            
            return True
            
        except Exception as e:
            logger.error("Exception publishing to %s: %s", topic, e)
            return False
    
    def publish_sensor(self, config: EntityConfig) -> bool:
        """Publish a sensor entity via MQTT Discovery.
        
        Args:
            config: Entity configuration
            
        Returns:
            True if published successfully
        """
        return self._publish_entity("sensor", config)
    
    def publish_binary_sensor(self, config: EntityConfig) -> bool:
        """Publish a binary sensor entity via MQTT Discovery.
        
        Args:
            config: Entity configuration (state should be "ON" or "OFF")
            
        Returns:
            True if published successfully
        """
        return self._publish_entity("binary_sensor", config)
    
    def _publish_entity(self, component: str, config: EntityConfig) -> bool:
        """Publish an entity via MQTT Discovery.
        
        Args:
            component: HA component type (sensor, binary_sensor, etc.)
            config: Entity configuration
            
        Returns:
            True if published successfully
        """
        unique_id = self._unique_id(config.object_id)
        state_topic = self._state_topic(component, config.object_id)
        
        # Build discovery payload
        discovery_payload = {
            "name": config.name,
            "unique_id": unique_id,
            "state_topic": state_topic,
            "device": self.device_info,
        }
        
        # Add optional fields
        if config.unit_of_measurement:
            discovery_payload["unit_of_measurement"] = config.unit_of_measurement
        if config.device_class:
            discovery_payload["device_class"] = config.device_class
        if config.state_class:
            discovery_payload["state_class"] = config.state_class
        if config.icon:
            discovery_payload["icon"] = config.icon
        if config.entity_category:
            discovery_payload["entity_category"] = config.entity_category
        if not config.enabled_by_default:
            discovery_payload["enabled_by_default"] = False
        
        # Add JSON attributes topic if we have attributes
        if config.attributes:
            attributes_topic = self._attributes_topic(component, config.object_id)
            discovery_payload["json_attributes_topic"] = attributes_topic
        
        # Publish discovery config
        discovery_topic = self._discovery_topic(component, config.object_id)
        if not self._publish(discovery_topic, discovery_payload):
            return False
        
        # Publish current state
        if not self._publish(state_topic, config.state):
            return False
        
        # Publish attributes if any
        if config.attributes:
            attributes_topic = self._attributes_topic(component, config.object_id)
            if not self._publish(attributes_topic, config.attributes):
                return False
        
        self._published_entities.append(f"{component}.{self.addon_id}_{config.object_id}")
        logger.debug("Published %s entity: %s (unique_id=%s)", component, config.name, unique_id)
        
        return True
    
    def _command_topic(self, component: str, object_id: str) -> str:
        """Get command topic for controllable entities."""
        return f"{self.addon_id}/{component}/{object_id}/set"
    
    def publish_number(self, config: NumberConfig, command_callback: Optional[callable] = None) -> bool:
        """Publish a number entity via MQTT Discovery.
        
        Args:
            config: Number entity configuration
            command_callback: Optional callback function(value: float) for commands
            
        Returns:
            True if published successfully
        """
        unique_id = self._unique_id(config.object_id)
        state_topic = self._state_topic("number", config.object_id)
        command_topic = self._command_topic("number", config.object_id)
        
        # Build discovery payload
        discovery_payload = {
            "name": config.name,
            "unique_id": unique_id,
            "state_topic": state_topic,
            "command_topic": command_topic,
            "min": config.min_value,
            "max": config.max_value,
            "step": config.step,
            "mode": config.mode,
            "device": self.device_info,
        }
        
        if config.unit_of_measurement:
            discovery_payload["unit_of_measurement"] = config.unit_of_measurement
        if config.device_class:
            discovery_payload["device_class"] = config.device_class
        if config.icon:
            discovery_payload["icon"] = config.icon
        if config.entity_category:
            discovery_payload["entity_category"] = config.entity_category
        
        # Publish discovery config
        discovery_topic = self._discovery_topic("number", config.object_id)
        if not self._publish(discovery_topic, discovery_payload):
            return False
        
        # Publish current state
        if not self._publish(state_topic, config.state):
            return False
        
        # Subscribe to command topic if callback provided
        if command_callback and self._client:
            self._subscribe_command(command_topic, lambda msg: command_callback(float(msg)))
        
        self._published_entities.append(f"number.{self.addon_id}_{config.object_id}")
        logger.debug("Published number entity: %s (unique_id=%s)", config.name, unique_id)
        
        return True
    
    def publish_select(self, config: SelectConfig, command_callback: Optional[callable] = None) -> bool:
        """Publish a select entity via MQTT Discovery.
        
        Args:
            config: Select entity configuration
            command_callback: Optional callback function(option: str) for commands
            
        Returns:
            True if published successfully
        """
        unique_id = self._unique_id(config.object_id)
        state_topic = self._state_topic("select", config.object_id)
        command_topic = self._command_topic("select", config.object_id)
        
        # Build discovery payload
        discovery_payload = {
            "name": config.name,
            "unique_id": unique_id,
            "state_topic": state_topic,
            "command_topic": command_topic,
            "options": config.options,
            "device": self.device_info,
        }
        
        if config.icon:
            discovery_payload["icon"] = config.icon
        if config.entity_category:
            discovery_payload["entity_category"] = config.entity_category
        
        # Publish discovery config
        discovery_topic = self._discovery_topic("select", config.object_id)
        if not self._publish(discovery_topic, discovery_payload):
            return False
        
        # Publish current state
        if not self._publish(state_topic, config.state):
            return False
        
        # Subscribe to command topic if callback provided
        if command_callback and self._client:
            self._subscribe_command(command_topic, command_callback)
        
        self._published_entities.append(f"select.{self.addon_id}_{config.object_id}")
        logger.debug("Published select entity: %s (unique_id=%s)", config.name, unique_id)
        
        return True
    
    def publish_button(self, config: ButtonConfig, press_callback: Optional[callable] = None) -> bool:
        """Publish a button entity via MQTT Discovery.
        
        Args:
            config: Button entity configuration
            press_callback: Optional callback function() for button press
            
        Returns:
            True if published successfully
        """
        unique_id = self._unique_id(config.object_id)
        command_topic = self._command_topic("button", config.object_id)
        
        # Build discovery payload - buttons don't have state_topic
        discovery_payload = {
            "name": config.name,
            "unique_id": unique_id,
            "command_topic": command_topic,
            "device": self.device_info,
        }
        
        if config.device_class:
            discovery_payload["device_class"] = config.device_class
        if config.icon:
            discovery_payload["icon"] = config.icon
        if config.entity_category:
            discovery_payload["entity_category"] = config.entity_category
        
        # Publish discovery config
        discovery_topic = self._discovery_topic("button", config.object_id)
        if not self._publish(discovery_topic, discovery_payload):
            return False
        
        # Subscribe to command topic if callback provided
        if press_callback and self._client:
            self._subscribe_command(command_topic, lambda msg: press_callback())
        
        self._published_entities.append(f"button.{self.addon_id}_{config.object_id}")
        logger.debug("Published button entity: %s (unique_id=%s)", config.name, unique_id)
        
        return True
    
    def publish_text(self, config: TextConfig, command_callback: Optional[callable] = None) -> bool:
        """Publish a text entity via MQTT Discovery.
        
        Args:
            config: Text entity configuration
            command_callback: Optional callback function(text: str) for commands
            
        Returns:
            True if published successfully
        """
        unique_id = self._unique_id(config.object_id)
        state_topic = self._state_topic("text", config.object_id)
        command_topic = self._command_topic("text", config.object_id)
        
        # Build discovery payload
        discovery_payload = {
            "name": config.name,
            "unique_id": unique_id,
            "state_topic": state_topic,
            "command_topic": command_topic,
            "min": config.min_length,
            "max": config.max_length,
            "mode": config.mode,
            "device": self.device_info,
        }
        
        if config.pattern:
            discovery_payload["pattern"] = config.pattern
        if config.icon:
            discovery_payload["icon"] = config.icon
        if config.entity_category:
            discovery_payload["entity_category"] = config.entity_category
        
        # Publish discovery config
        discovery_topic = self._discovery_topic("text", config.object_id)
        if not self._publish(discovery_topic, discovery_payload):
            return False
        
        # Publish current state
        if not self._publish(state_topic, config.state):
            return False
        
        # Subscribe to command topic if callback provided
        if command_callback and self._client:
            self._subscribe_command(command_topic, command_callback)
        
        self._published_entities.append(f"text.{self.addon_id}_{config.object_id}")
        logger.debug("Published text entity: %s (unique_id=%s)", config.name, unique_id)
        
        return True
    
    def _subscribe_command(self, topic: str, callback: callable):
        """Subscribe to a command topic with a callback.
        
        Args:
            topic: MQTT topic to subscribe to
            callback: Function to call with message payload (str)
        """
        if not self._client:
            return
        
        # Store callback for this topic
        if not hasattr(self, '_command_callbacks'):
            self._command_callbacks: Dict[str, callable] = {}
            # Set up the message handler
            self._client.on_message = self._on_message
        
        self._command_callbacks[topic] = callback
        self._client.subscribe(topic, qos=1)
        logger.debug("Subscribed to command topic: %s", topic)
    
    def _on_message(self, client, userdata, message):
        """Handle incoming MQTT messages."""
        topic = message.topic
        payload = message.payload.decode('utf-8')
        
        if hasattr(self, '_command_callbacks') and topic in self._command_callbacks:
            try:
                self._command_callbacks[topic](payload)
            except Exception as e:
                logger.error("Error handling command on %s: %s", topic, e)

    def update_state(self, component: str, object_id: str, state: str, attributes: Optional[Dict[str, Any]] = None) -> bool:
        """Update state for an existing entity.
        
        This only updates the state (and optionally attributes), not the discovery config.
        Use this for frequent state updates after initial discovery.
        
        Args:
            component: HA component type (sensor, binary_sensor, etc.)
            object_id: Object ID of the entity
            state: New state value
            attributes: Optional updated attributes
            
        Returns:
            True if published successfully
        """
        state_topic = self._state_topic(component, object_id)
        if not self._publish(state_topic, state):
            return False
        
        if attributes:
            attributes_topic = self._attributes_topic(component, object_id)
            if not self._publish(attributes_topic, attributes):
                return False
        
        return True
    
    def remove_entity(self, component: str, object_id: str) -> bool:
        """Remove an entity by publishing empty discovery config.
        
        Args:
            component: HA component type (sensor, binary_sensor, etc.)
            object_id: Object ID of the entity
            
        Returns:
            True if published successfully
        """
        discovery_topic = self._discovery_topic(component, object_id)
        return self._publish(discovery_topic, "")
    
    def get_published_entities(self) -> List[str]:
        """Get list of entity IDs published in this session."""
        return self._published_entities.copy()


def get_mqtt_config_from_env() -> Dict[str, Any]:
    """Get MQTT configuration from environment variables.
    
    Checks for common Home Assistant add-on environment patterns.
    
    Returns:
        Dictionary with mqtt_host, mqtt_port, mqtt_user, mqtt_password
    """
    return {
        "mqtt_host": os.getenv("MQTT_HOST", "core-mosquitto"),
        "mqtt_port": int(os.getenv("MQTT_PORT", "1883")),
        "mqtt_user": os.getenv("MQTT_USER"),
        "mqtt_password": os.getenv("MQTT_PASSWORD"),
    }
