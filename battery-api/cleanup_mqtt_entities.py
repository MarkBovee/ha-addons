#!/usr/bin/env python3
"""Cleanup script to remove all battery_api MQTT Discovery entities.

This publishes empty payloads to the discovery topics, which tells HA to remove the entities.

Usage:
    python cleanup_mqtt_entities.py
"""

import os
import time
from dotenv import load_dotenv
import paho.mqtt.client as mqtt

# Load .env
load_dotenv()
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

MQTT_HOST = os.getenv('MQTT_HOST', '192.168.1.135')
MQTT_PORT = int(os.getenv('MQTT_PORT', '1883'))
MQTT_USER = os.getenv('MQTT_USER', '')
MQTT_PASSWORD = os.getenv('MQTT_PASSWORD', '')

ADDON_ID = "battery_api"
DISCOVERY_PREFIX = "homeassistant"

# All known entity object_ids that may exist (old and new)
ENTITIES_TO_REMOVE = [
    # Sensors
    ("sensor", "battery_soc"),
    ("sensor", "battery_power"),
    ("sensor", "pv_power"),
    ("sensor", "grid_power"),
    ("sensor", "load_power"),
    ("sensor", "api_status"),
    ("sensor", "schedule_status"),
    ("sensor", "last_applied"),
    ("sensor", "current_schedule"),
    ("sensor", "battery_mode"),  # Old sensor version
    
    # Select entities
    ("select", "battery_mode"),
    ("select", "battery_mode_setting"),  # Old name
    
    # Text entities
    ("text", "schedule"),
    ("text", "charge_schedule"),  # Old v0.1.x
    ("text", "discharge_schedule"),  # Old v0.1.x
    
    # Number entities (if any existed)
    ("number", "charge_power"),
    ("number", "discharge_power"),
    
    # Button entities (if any existed)
    ("button", "apply_schedule"),
]


def main():
    print("=" * 60)
    print("Battery API MQTT Entity Cleanup")
    print("=" * 60)
    print(f"MQTT Broker: {MQTT_HOST}:{MQTT_PORT}")
    print(f"Addon ID: {ADDON_ID}")
    print()
    
    # Connect to MQTT
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    
    if MQTT_USER:
        client.username_pw_set(MQTT_USER, MQTT_PASSWORD)
    
    connected = False
    
    def on_connect(client, userdata, flags, reason_code, properties=None):
        nonlocal connected
        if reason_code == 0:
            print("✓ Connected to MQTT broker")
            connected = True
        else:
            print(f"✗ Failed to connect: {reason_code}")
    
    client.on_connect = on_connect
    
    try:
        client.connect(MQTT_HOST, MQTT_PORT, 60)
        client.loop_start()
        
        # Wait for connection
        for _ in range(50):  # 5 seconds
            if connected:
                break
            time.sleep(0.1)
        
        if not connected:
            print("✗ Could not connect to MQTT broker")
            return 1
        
        # Publish empty payloads to remove entities
        print(f"\nRemoving {len(ENTITIES_TO_REMOVE)} entities...")
        
        for component, object_id in ENTITIES_TO_REMOVE:
            topic = f"{DISCOVERY_PREFIX}/{component}/{ADDON_ID}/{object_id}/config"
            
            # Publish empty payload with retain=True to clear retained discovery config
            result = client.publish(topic, payload="", retain=True)
            result.wait_for_publish()
            
            print(f"  ✓ Removed {component}.{ADDON_ID}_{object_id}")
        
        # Give MQTT time to process
        time.sleep(1)
        
        print("\n" + "=" * 60)
        print("✓ Cleanup complete!")
        print()
        print("Now in Home Assistant:")
        print("1. Go to Settings → Devices & Services → MQTT")
        print("2. Click on 'Battery API' device (if still there)")
        print("3. Delete the device if it still exists")
        print("4. Restart the battery-api add-on to recreate fresh entities")
        print("=" * 60)
        
    except Exception as e:
        print(f"✗ Error: {e}")
        return 1
    finally:
        client.loop_stop()
        client.disconnect()
    
    return 0


if __name__ == "__main__":
    exit(main())
