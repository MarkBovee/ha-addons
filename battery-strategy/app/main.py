import sys
import os
import time
import argparse
import logging
import json
import datetime
import signal

# Add parent directory to path to allow importing shared modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.addon_base import setup_logging, setup_signal_handlers, sleep_with_shutdown_check
from shared.config_loader import load_addon_config, get_run_once_mode
from shared.ha_api import HomeAssistantApi, get_ha_api_config
from shared.mqtt_setup import setup_mqtt_client

from app.solar_monitor import SolarMonitor
from app.gap_scheduler import GapScheduler

logger = logging.getLogger("BatteryStrategy")

def main():
    # Parse args
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Run without publishing commands")
    args = parser.parse_args()

    # Setup
    setup_logging("battery-strategy")
    shutdown_event = setup_signal_handlers(logger)
    
    # Config
    try:
        config = load_addon_config(
            config_path="/data/options.json",
            defaults={
                "update_interval": 60,
                "passive_solar_enabled": True
            }
        )
    except Exception as e:
        logger.error(f"Failed to load config: {e}")
        sys.exit(1)

    # HA API
    try:
        ha_config = get_ha_api_config()
        ha_api = HomeAssistantApi(ha_config["url"], ha_config["token"], logger)
    except Exception as e:
        logger.error(f"Failed to setup HA API: {e}")
        sys.exit(1)

    # MQTT
    mqtt_client = None
    if not args.dry_run:
        mqtt_client = setup_mqtt_client(
            addon_name="Battery Strategy",
            addon_id="battery_strategy",
            config=config # Optional
        )
        if not mqtt_client:
            logger.warning("MQTT not available. Strategy will run but strictly in log-only mode.")
    else:
        logger.info("DRY RUN MODE: No MQTT commands will be sent.")

    # Modules
    solar_monitor = SolarMonitor(config, logger)
    gap_scheduler = GapScheduler(logger)

    # Main Loop
    run_once = get_run_once_mode()
    
    logger.info("Battery Strategy Optimizer started.")
    
    while not shutdown_event.is_set():
        try:
            # 1. Check Passive Solar State
            is_passive = solar_monitor.check_passive_state(ha_api)
            
            if is_passive:
                # 2. Generate Gap Schedule
                payload = gap_scheduler.generate_passive_gap_schedule()
                
                # 3. Publish
                topic = "battery_api/text/schedule/set"
                if mqtt_client:
                    # We use the raw publish method if available or assuming mqtt_setup gives us a client with publish
                    # shared.mqtt_setup returns a client wrapper usually.
                    # Usually it's client.publish(topic, payload)
                    logger.info(f"Command: {topic} -> {payload}")
                    mqtt_client.client.publish(topic, payload)
                else:
                    logger.info(f"[DRY-RUN] Would publish to {topic}: {payload}")
            else:
                # Normal Strategy (Price-based)
                # Placeholder for now
                pass
                # logger.debug("Normal strategy active (Noop)")

        except Exception as e:
            logger.error(f"Error in main loop: {e}", exc_info=True)

        if run_once:
            break
            
        sleep_with_shutdown_check(shutdown_event, config["update_interval"], logger)

if __name__ == "__main__":
    main()
