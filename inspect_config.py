import paho.mqtt.client as mqtt
import os
import json
import time

# Load env variables (same simplified logic as force_cleanup)
env_path = os.path.join(os.path.basename(".env"))
if os.path.exists(".env"):
    with open(".env", "r") as f:
        for line in f:
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.strip().split("=", 1)
                os.environ.setdefault(k, v)

MQTT_HOST = os.getenv("MQTT_HOST", "core-mosquitto")
MQTT_PORT = int(os.getenv("MQTT_PORT", 1883))
MQTT_USER = os.getenv("MQTT_USER")
MQTT_PASSWORD = os.getenv("MQTT_PASSWORD")

TOPIC = "homeassistant/sensor/battery_manager/status/config"

def on_connect(client, userdata, flags, result_code, properties=None):
    rc = result_code.value if hasattr(result_code, 'value') else result_code
    if rc == 0:
        print(f"Connected to {MQTT_HOST}. Subscribing to {TOPIC}...")
        client.subscribe(TOPIC)
    else:
        print(f"Failed to connect: {rc}")

def on_message(client, userdata, msg):
    print(f"\n--- TOPIC: {msg.topic} ---")
    try:
        payload = msg.payload.decode()
        if not payload:
             print("PAYLOAD: [EMPTY/NULL]")
        else:
             data = json.loads(payload)
             print(json.dumps(data, indent=2))
    except Exception as e:
        print(f"RAW PAYLOAD: {msg.payload}")
        print(f"Error decoding: {e}")
    
    # We got what we came for
    client.disconnect()
    os._exit(0)

client = mqtt.Client(protocol=mqtt.MQTTv311)
if MQTT_USER and MQTT_PASSWORD:
    client.username_pw_set(MQTT_USER, MQTT_PASSWORD)

client.on_connect = on_connect
client.on_message = on_message

client.connect(MQTT_HOST, MQTT_PORT, 60)
client.loop_forever()
