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
    return os.environ.get("HA_API_URL", "http://supervisor/core/api")


def get_ha_api_token() -> Optional[str]:
    """Get Home Assistant API token from environment."""
    return os.environ.get("HA_API_TOKEN") or os.environ.get("SUPERVISOR_TOKEN")


def delete_entity(entity_id: str, ha_api_url: str, ha_api_token: str) -> bool:
    """Delete a Home Assistant entity."""
    try:
        url = f"{ha_api_url}/states/{entity_id}"
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
        url = f"{ha_api_url}/states/{entity_id}"
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
    verbose: bool = True,
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

    # Log summary of created entities
    logger.info(f"Successfully created/updated {len(created_entities)} entities:")
    for entity_id in created_entities:
        logger.info(f"  - {entity_id}")


def update_charger_status(
    charger_api: ChargerApi, ha_api_url: str, ha_api_token: str, verbose: bool = False
) -> bool:
    """Update charger status and Home Assistant entities."""
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

    # Validate configuration
    if not email or not password:
        logger.error("Missing required configuration: email and password must be set")
        sys.exit(1)

    if not ha_api_token:
        logger.error("Missing Home Assistant API token")
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
    logger.info(f"Home Assistant API URL: {ha_api_url}")

    # Initialize API client
    charger_api = ChargerApi(email, password, host_name, base_url)

    # Authenticate
    if not charger_api.authenticate():
        logger.error("Failed to authenticate with Charge Amps API")
        sys.exit(1)

    logger.info("Successfully authenticated with Charge Amps API")

    # Delete old entities before creating new ones
    delete_old_entities(ha_api_url, ha_api_token)

    # Initial update (with verbose entity logging)
    logger.info("Performing initial charger status update...")
    update_charger_status(charger_api, ha_api_url, ha_api_token, verbose=True)

    # Main loop
    update_interval_seconds = update_interval * 60
    logger.info(f"Starting update loop (every {update_interval} minutes)...")

    while not shutdown_flag:
        try:
            time.sleep(update_interval_seconds)

            if shutdown_flag:
                break

            logger.info("Updating charger status...")
            update_charger_status(charger_api, ha_api_url, ha_api_token)

        except KeyboardInterrupt:
            logger.info("Received keyboard interrupt, stopping...")
            break
        except Exception as ex:
            logger.error(f"Error in update loop: {ex}", exc_info=True)
            # Continue loop even on error

    logger.info("EV Charger Monitor addon stopped")


if __name__ == "__main__":
    main()
