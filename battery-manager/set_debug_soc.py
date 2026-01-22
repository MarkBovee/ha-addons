import os
import sys
import logging

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "shared"))
from ha_api import HomeAssistantApi, get_ha_api_config
from dotenv import load_dotenv

def main():
    load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger("set_soc")
    
    url, token = get_ha_api_config()
    api = HomeAssistantApi(url, token)
    
    # Create a debug sensor with 50.0 to match C# fallback
    entity_id = "sensor.debug_fixed_soc"
    api.create_or_update_entity(entity_id, "50.0", {
        "friendly_name": "Debug Fixed SOC",
        "unit_of_measurement": "%",
        "device_class": "battery"
    })
    print(f"Set {entity_id} to 50.0")

if __name__ == "__main__":
    main()
