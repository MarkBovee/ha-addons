import requests, os, json
from dotenv import load_dotenv
from pathlib import Path
load_dotenv(Path(__file__).parent.parent / ".env")
token = os.getenv("HA_API_TOKEN")
base = os.getenv("HA_API_URL")
h = {"Authorization": f"Bearer {token}"}
r = requests.get(f"{base}/config", headers=h, timeout=10)
d = r.json()
print(f"HA version: {d.get('version', '?')}")

# Also check what the charge-amps MQTT discovery topics look like
import paho.mqtt.client as mqtt
import time

mqtt_host = os.getenv("MQTT_HOST", "core-mosquitto")
if mqtt_host == "core-mosquitto":
    mqtt_host = "192.168.1.135"

topics = []
def on_message(client, userdata, message):
    if message.payload:
        try:
            p = json.loads(message.payload.decode())
            topics.append((message.topic, p.get("object_id", "<not set>"), p.get("unique_id", ""), p.get("name", "")))
        except:
            pass

def on_connect(client, userdata, flags, rc, properties=None):
    # Subscribe to ALL addons' discovery topics
    client.subscribe("homeassistant/#")

client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
if os.getenv("MQTT_USER"):
    client.username_pw_set(os.getenv("MQTT_USER"), os.getenv("MQTT_PASSWORD"))
client.on_connect = on_connect
client.on_message = on_message
client.connect(mqtt_host, int(os.getenv("MQTT_PORT", 1883)), 60)
client.loop_start()
time.sleep(5)
client.loop_stop()
client.disconnect()

# Filter to our addons
our_topics = [t for t in topics if any(a in t[0] for a in ["charge_amps", "energy_prices", "battery_manager", "battery_api", "water_heater"])]
print(f"\nFound {len(our_topics)} discovery topics for our addons:\n")
for topic, oid, uid, name in sorted(our_topics):
    print(f"  {topic}")
    print(f"    object_id={oid}  unique_id={uid}  name={name}")
