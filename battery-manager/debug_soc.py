import os
import sys
import logging
from pprint import pprint

# Add shared folder to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "shared"))

from ha_api import HomeAssistantApi, get_ha_api_config
from dotenv import load_dotenv

def main():
    # Load env from root .env if exists (for local testing)
    load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))
    
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger("debug_soc")
    
    url, token = get_ha_api_config()
    api = HomeAssistantApi(url, token)
    
    # 1. Check the summary sensor used by Python app
    summary_entity = "sensor.battery_api_battery_soc"
    summary_state = api.get_entity_state(summary_entity)
    print(f"\n--- Python App Source ---")
    print(f"{summary_entity}: {summary_state.get('state', 'N/A')}{summary_state.get('attributes', {}).get('unit_of_measurement', '')}")
    
    # 2. Check the sensors used by C# app
    # C# Names:
    # BatteryB2n0200j2403e01735BatSoc
    # BatteryB2u4250j2511e06231BatSoc ... etc
    # These typically map to snake_case in HA
    
    csharp_sensors = [
        "sensor.battery_b2n0200j2403e01735_bat_soc",
        "sensor.battery_b2u4250j2511e06231_bat_soc",
        "sensor.battery_b2u4250j2511e06243_bat_soc", 
        "sensor.battery_b2u4250j2511e06244_bat_soc",
        "sensor.battery_b2u4250j2511e06245_bat_soc",
        "sensor.battery_b2u4250j2511e06247_bat_soc"
    ]
    
    print(f"\n--- C# App Sources ---")
    valid_values = []
    for sensor in csharp_sensors:
        data = api.get_entity_state(sensor)
        if data:
            state = data.get('state')
            print(f"{sensor}: {state}")
            
            # Try to parse as float
            try:
                val = float(state)
                valid_values.append(val)
            except (ValueError, TypeError):
                pass
        else:
            print(f"{sensor}: NOT FOUND")
            
    print(f"\n--- C# Logic Emulation ---")
    if valid_values:
        avg = sum(valid_values) / len(valid_values)
        print(f"Valid sensors: {len(valid_values)}")
        print(f"Calculated Average: {avg}")
    else:
        print("Valid sensors: 0")
        print("Fallback value: 50.0 (This explains why C# sees 50%)")

if __name__ == "__main__":
    main()
