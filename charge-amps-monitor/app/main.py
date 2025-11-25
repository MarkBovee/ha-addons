"""Main application for EV Charger Monitor addon."""

import logging
import os
import signal
import sys
import time
from typing import Optional

import requests

from .charger_api import ChargerApi
from .models import ChargePoint, Connector

# Try to import MQTT Discovery module
try:
    from shared.ha_mqtt_discovery import MqttDiscovery, EntityConfig, get_mqtt_config_from_env
    MQTT_AVAILABLE = True
except ImportError:
    MQTT_AVAILABLE = False

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Global flag for graceful shutdown
shutdown_flag = False


def signal_handler(signum, frame):
    """Handle shutdown signals."""
    global shutdown_flag
    logger.info("Received shutdown signal, stopping...")
    shutdown_flag = True


def get_ha_api_url() -> str:
    """Get Home Assistant API URL from environment."""
    return os.environ.get("HA_API_URL", "http://supervisor/core")


def get_ha_api_token() -> Optional[str]:
    """Get Home Assistant API token from environment."""
    return os.environ.get("HA_API_TOKEN") or os.environ.get("SUPERVISOR_TOKEN")


def delete_entity(entity_id: str, ha_api_url: str, ha_api_token: str) -> bool:
    """Delete a Home Assistant entity."""
    try:
        url = f"{ha_api_url}/api/states/{entity_id}"
        headers = {
            "Authorization": f"Bearer {ha_api_token}",
            "Content-Type": "application/json",
        }

        response = requests.delete(url, headers=headers, timeout=10)

        if response.ok:
            logger.info(f"Deleted entity: {entity_id}")
            return True
        else:
            # Entity might not exist, which is fine
            logger.debug(
                f"Entity {entity_id} not found or already deleted: {response.status_code}"
            )
            return False

    except Exception as ex:
        logger.debug(f"Exception deleting entity {entity_id}: {ex}")
        return False


def create_or_update_entity(
    entity_id: str,
    state: str,
    attributes: dict,
    ha_api_url: str,
    ha_api_token: str,
    log_success: bool = True,
) -> bool:
    """Create or update a Home Assistant entity."""
    try:
        url = f"{ha_api_url}/api/states/{entity_id}"
        headers = {
            "Authorization": f"Bearer {ha_api_token}",
            "Content-Type": "application/json",
        }
        payload = {"state": state, "attributes": attributes}

        response = requests.post(url, json=payload, headers=headers, timeout=10)

        if response.ok:
            if log_success:
                friendly_name = attributes.get("friendly_name", entity_id)
                logger.info(
                    f"Created/updated entity: {entity_id} ({friendly_name}) = {state}"
                )
            return True
        else:
            # Log more details for 401 errors
            if response.status_code == 401:
                logger.error(
                    f"Failed to update entity {entity_id}: 401 Unauthorized. "
                    f"Token present: {'YES' if ha_api_token else 'NO'}, "
                    f"URL: {url}, "
                    f"Response: {response.text[:200]}"
                )
            else:
                logger.error(
                    f"Failed to update entity {entity_id}: {response.status_code} - {response.text}"
                )
            return False

    except Exception as ex:
        logger.error(f"Exception updating entity {entity_id}: {ex}", exc_info=True)
        return False


def delete_old_entities(ha_api_url: str, ha_api_token: str):
    """Delete old entities that don't have the ca_ prefix."""
    old_entities = [
        "input_boolean.charger_charging",
        "input_number.charger_total_consumption_kwh",
        "input_number.charger_current_power_w",
        "sensor.charger_status",
        "sensor.charger_power_kw",
        "sensor.charger_voltage",
        "sensor.charger_current",
        "binary_sensor.charger_online",
        "binary_sensor.charger_connector_enabled",
        "input_text.charger_name",
        "input_text.charger_serial",
        "sensor.charger_connector_mode",
        "sensor.charger_ocpp_status",
        "sensor.charger_error_code",
    ]

    logger.info("Cleaning up old entities...")
    deleted_count = 0
    for entity_id in old_entities:
        if delete_entity(entity_id, ha_api_url, ha_api_token):
            deleted_count += 1

    if deleted_count > 0:
        logger.info(f"Deleted {deleted_count} old entities")
    else:
        logger.info("No old entities found to delete")


def create_entities(
    charge_point: ChargePoint,
    connector: Connector,
    ha_api_url: str,
    ha_api_token: str,
    verbose: bool = False,
):
    """Create or update all Home Assistant entities."""
    if not charge_point or not connector:
        logger.warning("Cannot create entities: missing charge point or connector data")
        return

    if verbose:
        logger.info("Creating/updating Home Assistant entities...")
    created_entities = []

    # Basic entities (from Charger.cs example)
    if create_or_update_entity(
        "input_boolean.ca_charger_charging",
        "on" if connector.is_charging else "off",
        {"friendly_name": "Charger Charging", "icon": "mdi:ev-station"},
        ha_api_url,
        ha_api_token,
        log_success=verbose,
    ):
        created_entities.append("input_boolean.ca_charger_charging")

    if create_or_update_entity(
        "input_number.ca_charger_total_consumption_kwh",
        str(connector.total_consumption_kwh),
        {
            "friendly_name": "Charger Total Consumption",
            "unit_of_measurement": "kWh",
            "icon": "mdi:lightning-bolt",
        },
        ha_api_url,
        ha_api_token,
        log_success=verbose,
    ):
        created_entities.append("input_number.ca_charger_total_consumption_kwh")

    if create_or_update_entity(
        "input_number.ca_charger_current_power_w",
        str(connector.current_power_w),
        {
            "friendly_name": "Charger Current Power",
            "unit_of_measurement": "W",
            "icon": "mdi:flash",
        },
        ha_api_url,
        ha_api_token,
        log_success=verbose,
    ):
        created_entities.append("input_number.ca_charger_current_power_w")

    # Additional sensor entities
    if create_or_update_entity(
        "sensor.ca_charger_status",
        charge_point.charge_point_status or "unknown",
        {"friendly_name": "Charger Status", "icon": "mdi:information"},
        ha_api_url,
        ha_api_token,
        log_success=verbose,
    ):
        created_entities.append("sensor.ca_charger_status")

    if create_or_update_entity(
        "sensor.ca_charger_power_kw",
        str(connector.current_power_w / 1000.0),
        {
            "friendly_name": "Charger Power",
            "unit_of_measurement": "kW",
            "device_class": "power",
            "icon": "mdi:flash",
        },
        ha_api_url,
        ha_api_token,
        log_success=verbose,
    ):
        created_entities.append("sensor.ca_charger_power_kw")

    # Calculate average voltage and current
    avg_voltage = (connector.voltage1 + connector.voltage2 + connector.voltage3) / 3.0
    avg_current = (connector.current1 + connector.current2 + connector.current3) / 3.0

    if avg_voltage > 0:
        if create_or_update_entity(
            "sensor.ca_charger_voltage",
            str(avg_voltage),
            {
                "friendly_name": "Charger Voltage",
                "unit_of_measurement": "V",
                "device_class": "voltage",
                "icon": "mdi:lightning-bolt",
            },
            ha_api_url,
            ha_api_token,
            log_success=verbose,
        ):
            created_entities.append("sensor.ca_charger_voltage")

    if avg_current > 0:
        if create_or_update_entity(
            "sensor.ca_charger_current",
            str(avg_current),
            {
                "friendly_name": "Charger Current",
                "unit_of_measurement": "A",
                "device_class": "current",
                "icon": "mdi:current-ac",
            },
            ha_api_url,
            ha_api_token,
            log_success=verbose,
        ):
            created_entities.append("sensor.ca_charger_current")

    # Binary sensors
    if create_or_update_entity(
        "binary_sensor.ca_charger_online",
        "on" if charge_point.is_online else "off",
        {
            "friendly_name": "Charger Online",
            "device_class": "connectivity",
            "icon": "mdi:network",
        },
        ha_api_url,
        ha_api_token,
        log_success=verbose,
    ):
        created_entities.append("binary_sensor.ca_charger_online")

    if create_or_update_entity(
        "binary_sensor.ca_charger_connector_enabled",
        "on" if connector.enabled else "off",
        {"friendly_name": "Charger Connector Enabled", "icon": "mdi:power"},
        ha_api_url,
        ha_api_token,
        log_success=verbose,
    ):
        created_entities.append("binary_sensor.ca_charger_connector_enabled")

    # Text entities for info
    if charge_point.name:
        if create_or_update_entity(
            "input_text.ca_charger_name",
            charge_point.name,
            {"friendly_name": "Charger Name", "icon": "mdi:ev-station"},
            ha_api_url,
            ha_api_token,
            log_success=verbose,
        ):
            created_entities.append("input_text.ca_charger_name")

    if charge_point.serial_number:
        if create_or_update_entity(
            "input_text.ca_charger_serial",
            charge_point.serial_number,
            {"friendly_name": "Charger Serial Number", "icon": "mdi:identifier"},
            ha_api_url,
            ha_api_token,
            log_success=verbose,
        ):
            created_entities.append("input_text.ca_charger_serial")

    # Additional status sensors
    if connector.mode:
        if create_or_update_entity(
            "sensor.ca_charger_connector_mode",
            connector.mode,
            {"friendly_name": "Charger Connector Mode", "icon": "mdi:cog"},
            ha_api_url,
            ha_api_token,
            log_success=verbose,
        ):
            created_entities.append("sensor.ca_charger_connector_mode")

    if connector.ocpp_status:
        if create_or_update_entity(
            "sensor.ca_charger_ocpp_status",
            connector.ocpp_status,
            {"friendly_name": "Charger OCPP Status", "icon": "mdi:network"},
            ha_api_url,
            ha_api_token,
            log_success=verbose,
        ):
            created_entities.append("sensor.ca_charger_ocpp_status")

    if connector.error_code:
        if create_or_update_entity(
            "sensor.ca_charger_error_code",
            connector.error_code,
            {"friendly_name": "Charger Error Code", "icon": "mdi:alert"},
            ha_api_url,
            ha_api_token,
            log_success=verbose,
        ):
            created_entities.append("sensor.ca_charger_error_code")

    # Log summary only when verbose to avoid spamming each update cycle
    if verbose:
        logger.info(f"Successfully created/updated {len(created_entities)} entities:")
        for entity_id in created_entities:
            logger.info(f"  - {entity_id}")


def create_entities_mqtt(
    charge_point: ChargePoint,
    connector: Connector,
    mqtt_client: 'MqttDiscovery',
    verbose: bool = False,
):
    """Create or update all Home Assistant entities via MQTT Discovery.
    
    This creates entities with proper unique_id support for UI management.
    """
    if not charge_point or not connector:
        logger.warning("Cannot create entities: missing charge point or connector data")
        return

    if verbose:
        logger.info("Creating/updating Home Assistant entities via MQTT Discovery...")
    
    created_entities = []
    
    # Charging binary sensor
    mqtt_client.publish_binary_sensor(EntityConfig(
        object_id="charging",
        name="Charger Charging",
        state="ON" if connector.is_charging else "OFF",
        device_class="plug",
        icon="mdi:ev-station",
    ))
    created_entities.append("charging")
    
    # Total consumption sensor
    mqtt_client.publish_sensor(EntityConfig(
        object_id="total_consumption",
        name="Charger Total Consumption",
        state=str(connector.total_consumption_kwh),
        unit_of_measurement="kWh",
        device_class="energy",
        state_class="total_increasing",
        icon="mdi:lightning-bolt",
    ))
    created_entities.append("total_consumption")
    
    # Current power sensor
    mqtt_client.publish_sensor(EntityConfig(
        object_id="current_power",
        name="Charger Current Power",
        state=str(connector.current_power_w),
        unit_of_measurement="W",
        device_class="power",
        state_class="measurement",
        icon="mdi:flash",
    ))
    created_entities.append("current_power")
    
    # Power in kW sensor
    mqtt_client.publish_sensor(EntityConfig(
        object_id="power_kw",
        name="Charger Power",
        state=str(connector.current_power_w / 1000.0),
        unit_of_measurement="kW",
        device_class="power",
        state_class="measurement",
        icon="mdi:flash",
    ))
    created_entities.append("power_kw")
    
    # Status sensor
    mqtt_client.publish_sensor(EntityConfig(
        object_id="status",
        name="Charger Status",
        state=charge_point.charge_point_status or "unknown",
        icon="mdi:information",
    ))
    created_entities.append("status")
    
    # Online binary sensor
    mqtt_client.publish_binary_sensor(EntityConfig(
        object_id="online",
        name="Charger Online",
        state="ON" if charge_point.is_online else "OFF",
        device_class="connectivity",
        icon="mdi:network",
    ))
    created_entities.append("online")
    
    # Connector enabled binary sensor
    mqtt_client.publish_binary_sensor(EntityConfig(
        object_id="connector_enabled",
        name="Charger Connector Enabled",
        state="ON" if connector.enabled else "OFF",
        icon="mdi:power",
    ))
    created_entities.append("connector_enabled")
    
    # Calculate average voltage and current
    avg_voltage = (connector.voltage1 + connector.voltage2 + connector.voltage3) / 3.0
    avg_current = (connector.current1 + connector.current2 + connector.current3) / 3.0
    
    if avg_voltage > 0:
        mqtt_client.publish_sensor(EntityConfig(
            object_id="voltage",
            name="Charger Voltage",
            state=str(round(avg_voltage, 1)),
            unit_of_measurement="V",
            device_class="voltage",
            state_class="measurement",
            icon="mdi:lightning-bolt",
        ))
        created_entities.append("voltage")
    
    if avg_current > 0:
        mqtt_client.publish_sensor(EntityConfig(
            object_id="current",
            name="Charger Current",
            state=str(round(avg_current, 1)),
            unit_of_measurement="A",
            device_class="current",
            state_class="measurement",
            icon="mdi:current-ac",
        ))
        created_entities.append("current")
    
    # Charger info sensors
    if charge_point.name:
        mqtt_client.publish_sensor(EntityConfig(
            object_id="name",
            name="Charger Name",
            state=charge_point.name,
            icon="mdi:ev-station",
            entity_category="diagnostic",
        ))
        created_entities.append("name")
    
    if charge_point.serial_number:
        mqtt_client.publish_sensor(EntityConfig(
            object_id="serial",
            name="Charger Serial Number",
            state=charge_point.serial_number,
            icon="mdi:identifier",
            entity_category="diagnostic",
        ))
        created_entities.append("serial")
    
    if connector.mode:
        mqtt_client.publish_sensor(EntityConfig(
            object_id="connector_mode",
            name="Charger Connector Mode",
            state=connector.mode,
            icon="mdi:cog",
            entity_category="diagnostic",
        ))
        created_entities.append("connector_mode")
    
    if connector.ocpp_status:
        mqtt_client.publish_sensor(EntityConfig(
            object_id="ocpp_status",
            name="Charger OCPP Status",
            state=connector.ocpp_status,
            icon="mdi:network",
            entity_category="diagnostic",
        ))
        created_entities.append("ocpp_status")
    
    if connector.error_code:
        mqtt_client.publish_sensor(EntityConfig(
            object_id="error_code",
            name="Charger Error Code",
            state=connector.error_code,
            icon="mdi:alert",
            entity_category="diagnostic",
        ))
        created_entities.append("error_code")
    
    if verbose:
        logger.info(f"Created {len(created_entities)} entities via MQTT Discovery:")
        logger.info("  Entities have unique_id and can be managed from HA UI")
        for entity_id in created_entities:
            logger.info(f"  - sensor.charge_amps_{entity_id}")


def update_entities_mqtt(
    charge_point: ChargePoint,
    connector: Connector,
    mqtt_client: 'MqttDiscovery',
):
    """Update entity states via MQTT (without republishing discovery config)."""
    if not charge_point or not connector:
        return
    
    # Update main sensors
    mqtt_client.update_state("binary_sensor", "charging", 
                             "ON" if connector.is_charging else "OFF")
    mqtt_client.update_state("sensor", "total_consumption", 
                             str(connector.total_consumption_kwh))
    mqtt_client.update_state("sensor", "current_power", 
                             str(connector.current_power_w))
    mqtt_client.update_state("sensor", "power_kw", 
                             str(connector.current_power_w / 1000.0))
    mqtt_client.update_state("sensor", "status", 
                             charge_point.charge_point_status or "unknown")
    mqtt_client.update_state("binary_sensor", "online", 
                             "ON" if charge_point.is_online else "OFF")
    mqtt_client.update_state("binary_sensor", "connector_enabled", 
                             "ON" if connector.enabled else "OFF")
    
    # Update voltage/current if available
    avg_voltage = (connector.voltage1 + connector.voltage2 + connector.voltage3) / 3.0
    avg_current = (connector.current1 + connector.current2 + connector.current3) / 3.0
    
    if avg_voltage > 0:
        mqtt_client.update_state("sensor", "voltage", str(round(avg_voltage, 1)))
    if avg_current > 0:
        mqtt_client.update_state("sensor", "current", str(round(avg_current, 1)))


def setup_mqtt_client() -> Optional['MqttDiscovery']:
    """Set up MQTT Discovery client if available.
    
    Returns:
        MqttDiscovery client if connected, None otherwise
    """
    if not MQTT_AVAILABLE:
        logger.info("MQTT Discovery not available (paho-mqtt not installed)")
        return None
    
    mqtt_config = get_mqtt_config_from_env()
    
    mqtt_host = os.getenv('MQTT_HOST', mqtt_config['mqtt_host'])
    mqtt_port = int(os.getenv('MQTT_PORT', mqtt_config['mqtt_port']))
    mqtt_user = os.getenv('MQTT_USER', mqtt_config['mqtt_user'])
    mqtt_password = os.getenv('MQTT_PASSWORD', mqtt_config['mqtt_password'])
    
    logger.info("Attempting MQTT Discovery connection to %s:%d...", mqtt_host, mqtt_port)
    
    try:
        mqtt_client = MqttDiscovery(
            addon_name="Charge Amps Monitor",
            addon_id="charge_amps",
            mqtt_host=mqtt_host,
            mqtt_port=mqtt_port,
            mqtt_user=mqtt_user,
            mqtt_password=mqtt_password,
            manufacturer="Charge Amps",
            model="EV Charger"
        )
        
        if mqtt_client.connect(timeout=10.0):
            logger.info("MQTT Discovery connected - entities will have unique_id")
            return mqtt_client
        else:
            logger.warning("MQTT connection failed, falling back to REST API")
            return None
            
    except Exception as e:
        logger.warning("MQTT setup failed (%s), falling back to REST API", e)
        return None


def update_charger_status(
    charger_api: ChargerApi, ha_api_url: str, ha_api_token: str, verbose: bool = False
) -> bool:
    """Update charger status and Home Assistant entities via REST API."""
    try:
        charge_points = charger_api.get_charge_points()

        if not charge_points or len(charge_points) == 0:
            logger.warning("No charge points found")
            return False

        # Get the first charge point (assuming single charger setup)
        charge_point = charge_points[0]
        connector = charge_point.connectors[0] if charge_point.connectors else None

        if not connector:
            logger.warning(f"No connector found on charge point {charge_point.id}")
            return False

        # Create/update all entities
        create_entities(
            charge_point, connector, ha_api_url, ha_api_token, verbose=verbose
        )

        logger.info(
            f"Charger status updated: {charge_point.name} - "
            f"Charging={connector.is_charging}, "
            f"TotalKwh={connector.total_consumption_kwh:.2f}, "
            f"Power={connector.current_power_w:.0f}W"
        )

        return True

    except Exception as ex:
        logger.error(f"Failed to update charger status: {ex}", exc_info=True)
        return False


def update_charger_status_mqtt(
    charger_api: ChargerApi, mqtt_client: 'MqttDiscovery', verbose: bool = False
) -> bool:
    """Update charger status via MQTT Discovery."""
    try:
        charge_points = charger_api.get_charge_points()

        if not charge_points or len(charge_points) == 0:
            logger.warning("No charge points found")
            return False

        charge_point = charge_points[0]
        connector = charge_point.connectors[0] if charge_point.connectors else None

        if not connector:
            logger.warning(f"No connector found on charge point {charge_point.id}")
            return False

        if verbose:
            # First run: publish full discovery config
            create_entities_mqtt(charge_point, connector, mqtt_client, verbose=True)
        else:
            # Subsequent runs: just update states
            update_entities_mqtt(charge_point, connector, mqtt_client)

        logger.info(
            f"Charger status updated (MQTT): {charge_point.name} - "
            f"Charging={connector.is_charging}, "
            f"TotalKwh={connector.total_consumption_kwh:.2f}, "
            f"Power={connector.current_power_w:.0f}W"
        )

        return True

    except Exception as ex:
        logger.error(f"Failed to update charger status via MQTT: {ex}", exc_info=True)
        return False


def main():
    """Main application entry point."""
    global shutdown_flag

    # Register signal handlers
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    # Get configuration from environment
    email = os.environ.get("CHARGER_EMAIL")
    password = os.environ.get("CHARGER_PASSWORD")
    host_name = os.environ.get("CHARGER_HOST_NAME", "my.charge.space")
    base_url = os.environ.get("CHARGER_BASE_URL", "https://my.charge.space")
    update_interval = int(os.environ.get("CHARGER_UPDATE_INTERVAL", "1"))

    ha_api_url = get_ha_api_url()
    ha_api_token = get_ha_api_token()
    
    mqtt_client = None

    # Validate configuration
    if not email or not password:
        logger.error("Missing required configuration: email and password must be set")
        sys.exit(1)

    logger.info("Starting EV Charger Monitor addon")
    # Mask email for security (only show first char and domain)
    if email:
        email_parts = email.split("@")
        if len(email_parts) == 2:
            masked_email = f"{email_parts[0][0]}***@{email_parts[1]}"
        else:
            masked_email = "***"
    else:
        masked_email = "NOT SET"
    logger.info(f"Email: {masked_email}")
    logger.info(f"Host Name: {host_name}")
    logger.info(f"Base URL: {base_url}")
    logger.info(f"Update Interval: {update_interval} minutes")

    # Initialize API client
    charger_api = ChargerApi(email, password, host_name, base_url)

    # Authenticate
    if not charger_api.authenticate():
        logger.error("Failed to authenticate with Charge Amps API")
        sys.exit(1)

    logger.info("Successfully authenticated with Charge Amps API")

    # Try MQTT Discovery first (provides unique_id for UI management)
    mqtt_client = setup_mqtt_client()
    use_mqtt = mqtt_client is not None

    if not use_mqtt:
        # Fall back to REST API
        if not ha_api_token:
            logger.error("Missing Home Assistant API token and MQTT not available")
            sys.exit(1)
        
        logger.info(f"Using REST API fallback: {ha_api_url}")
        
        # Test Home Assistant API connection
        try:
            test_url = f"{ha_api_url}/api/states"
            test_headers = {
                "Authorization": f"Bearer {ha_api_token}",
                "Content-Type": "application/json",
            }
            test_response = requests.get(test_url, headers=test_headers, timeout=10)
            if test_response.ok:
                logger.info("Home Assistant API connection successful")
            else:
                logger.warning(
                    f"Home Assistant API test failed: {test_response.status_code} - {test_response.text[:200]}"
                )
        except Exception as ex:
            logger.warning(f"Home Assistant API test exception: {ex}")

        # Delete old entities before creating new ones (REST API only)
        delete_old_entities(ha_api_url, ha_api_token)

    # Initial update (with verbose entity logging)
    logger.info("Performing initial charger status update...")
    if use_mqtt:
        update_charger_status_mqtt(charger_api, mqtt_client, verbose=True)
    else:
        update_charger_status(charger_api, ha_api_url, ha_api_token, verbose=True)

    # Main loop
    update_interval_seconds = update_interval * 60
    logger.info(f"Starting update loop (every {update_interval} minutes)...")

    try:
        while not shutdown_flag:
            try:
                time.sleep(update_interval_seconds)

                if shutdown_flag:
                    break

                logger.info("Updating charger status...")
                if use_mqtt and mqtt_client and mqtt_client.is_connected():
                    update_charger_status_mqtt(charger_api, mqtt_client)
                else:
                    update_charger_status(charger_api, ha_api_url, ha_api_token)

            except KeyboardInterrupt:
                logger.info("Received keyboard interrupt, stopping...")
                break
            except Exception as ex:
                logger.error(f"Error in update loop: {ex}", exc_info=True)
                # Continue loop even on error
    finally:
        # Clean up MQTT connection
        if mqtt_client:
            mqtt_client.disconnect()

    logger.info("EV Charger Monitor addon stopped")


if __name__ == "__main__":
    main()
