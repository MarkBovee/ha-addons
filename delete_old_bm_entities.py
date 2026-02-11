"""Delete old battery_manager_battery_manager_* entities from Home Assistant via MQTT."""

import os
import sys
from dotenv import load_dotenv
import paho.mqtt.client as mqtt

load_dotenv()

MQTT_HOST = os.getenv("MQTT_HOST", "192.168.1.135")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_USER = os.getenv("MQTT_USER")
MQTT_PASSWORD = os.getenv("MQTT_PASSWORD")

if not MQTT_USER or not MQTT_PASSWORD:
    print("Error: MQTT_USER or MQTT_PASSWORD not found in .env")
    sys.exit(1)

# Old object_ids that created doubled entities
OLD_OBJECT_IDS = [
    "status",
    "reasoning", 
    "forecast",
    "price_ranges",
    "current_action",
    "charge_schedule",
    "discharge_schedule",
    "schedule",
    "mode",
]

def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("✅ Connected to MQTT broker\n")
        print("Unpublishing old MQTT Discovery entities...\n")
        
        for object_id in OLD_OBJECT_IDS:
            # MQTT Discovery config topic format:
            # homeassistant/sensor/battery_manager/[object_id]/config
            topic = f"homeassistant/sensor/battery_manager/{object_id}/config"
            
            # Publish empty payload to unpublish (remove from HA)
            client.publish(topic, payload="", retain=True)
            print(f"🗑️  Unpublished: sensor.battery_manager_battery_manager_{object_id}")
        
        print("\n✅ Done! Old entities should disappear from HA within a few seconds.")
        client.disconnect()
    else:
        print(f"❌ MQTT connection failed with code {rc}")
        sys.exit(1)

# Create MQTT client
client = mqtt.Client(client_id="bm_entity_cleanup")
client.username_pw_set(MQTT_USER, MQTT_PASSWORD)
client.on_connect = on_connect

print(f"Connecting to MQTT broker at {MQTT_HOST}:{MQTT_PORT}...")
client.connect(MQTT_HOST, MQTT_PORT, 60)
client.loop_forever()
