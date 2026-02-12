import paho.mqtt.client as mqtt
import os
import time
import sys

# Try to load .env file if present
env_path = os.path.join(os.path.dirname(__file__), ".env")
if os.path.exists(env_path):
    print(f"Loading .env file from {env_path}...")
    try:
        with open(env_path, "r") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"): continue
                if "=" in line:
                    k, v = line.split("=", 1)
                    k, v = k.strip(), v.strip()
                    if k not in os.environ:
                        os.environ[k] = v
    except Exception as e:
        print(f"Warning: Failed to parse .env: {e}")

# Default to core-mosquitto if not set, but allow override
MQTT_HOST = os.getenv("MQTT_HOST", "core-mosquitto")
MQTT_PORT = int(os.getenv("MQTT_PORT", 1883))
MQTT_USER = os.getenv("MQTT_USER")
MQTT_PASSWORD = os.getenv("MQTT_PASSWORD")

# List of entities known to Battery Manager
ENTITIES = [
    "status", 
    "reasoning", 
    "forecast", 
    "price_ranges", 
    "current_action", 
    "charge_schedule", 
    "discharge_schedule", 
    "schedule", 
    "schedule_part_2", 
    "mode"
]

def on_connect(client, userdata, flags, result_code, properties=None):
    # Support both paho-mqtt v1 (int) and v2 (object) result codes
    rc = result_code.value if hasattr(result_code, 'value') else result_code
    if rc == 0:
        print(f"✅ Connected to MQTT broker at {MQTT_HOST}:{MQTT_PORT}")
    else:
        print(f"❌ Failed to connect, return code {rc}")
        sys.exit(1)

def on_publish(client, userdata, mid, reason_code=None, properties=None):
    pass

try:
    print(f"Connecting to MQTT broker at {MQTT_HOST}...")
    # Use protocol v3.1.1 for broad compatibility
    client = mqtt.Client(protocol=mqtt.MQTTv311)
    
    if MQTT_USER and MQTT_PASSWORD:
        client.username_pw_set(MQTT_USER, MQTT_PASSWORD)
    
    client.on_connect = on_connect
    client.on_publish = on_publish
    
    client.connect(MQTT_HOST, MQTT_PORT, 60)
    client.loop_start()
    
    # Wait for connection
    time.sleep(2)
    
    print("\n🧹 Starting cleanup of Battery Manager entities...")
    print("This will send empty retained messages to discovery topics to force-remove entities from HA.")
    
    count = 0
    
    for entity in ENTITIES:
        # 1. Clean standard sensor topics
        # This removes the entity definition from Home Assistant
        topic = f"homeassistant/sensor/battery_manager/{entity}/config"
        print(f"   Deleting: {topic}")
        client.publish(topic, "", retain=True)
        count += 1
        
        # 2. Clean potential double-prefixed topics (just in case they were created by manual experiments)
        topic_double = f"homeassistant/sensor/battery_manager/battery_manager_{entity}/config"
        # We don't print this to avoid confusion unless we are debugging, but harmless to send
        client.publish(topic_double, "", retain=True)
        
        # 3. Special case handling
        # 'mode' might have been a select or sensor. Clean both possible locations.
        if entity == "mode":
            topic_select = f"homeassistant/select/battery_manager/mode/config"
            print(f"   Deleting: {topic_select}")
            client.publish(topic_select, "", retain=True)
            count += 1

    print(f"\n✅ Sent {count} deletion commands.")
    print("⏳ Waiting 5 seconds for broker to process...")
    time.sleep(5)
    
    client.loop_stop()
    client.disconnect()
    print("\n🎉 Cleanup complete.")
    print("👉 ACTION REQUIRED: Restart Home Assistant Core now to clear the entity registry.")
    print("   After restart, the entities will reappear correctly when Battery Manager starts.")

except ImportError:
    print("❌ Error: paho-mqtt library not found. Please install it with 'pip install paho-mqtt'")
except Exception as e:
    print(f"❌ Error during cleanup: {e}")
