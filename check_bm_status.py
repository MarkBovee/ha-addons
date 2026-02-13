#!/usr/bin/env python3
"""Quick check of current battery-manager entities in HA."""
import os, json, requests
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(Path(__file__).parent / ".env")

token = os.getenv("HA_API_TOKEN")
base = os.getenv("HA_API_URL")
h = {"Authorization": f"Bearer {token}"}

r = requests.get(f"{base}/states", headers=h, timeout=10)
all_entities = r.json()

# Find BM entities - both prefixed and unprefixed
bm = [e for e in all_entities if 
      "battery_manager" in e["entity_id"] or 
      e["entity_id"] in [
          "sensor.status", "sensor.mode", "sensor.reasoning", "sensor.forecast",
          "sensor.price_ranges", "sensor.current_action", "sensor.charge_schedule",
          "sensor.discharge_schedule", "sensor.schedule", "sensor.schedule_part_2"
      ]]

print(f"Found {len(bm)} battery-manager related entities:\n")
for e in sorted(bm, key=lambda x: x["entity_id"]):
    print(f"  {e['entity_id']:50s} state={str(e['state'])[:40]}")

# Also check entity registry
print("\n--- Entity Registry ---")
reg_path = Path(r"\\192.168.1.135\config\.storage\core.entity_registry")
with open(reg_path) as f:
    data = json.load(f)

entities = data["data"]["entities"]
bm_reg = [e for e in entities if 
          "battery_manager" in str(e.get("unique_id", "")) and e.get("platform") == "mqtt"]
print(f"Found {len(bm_reg)} MQTT battery_manager entries in registry:\n")
for e in bm_reg:
    print(f"  {e['entity_id']:50s} unique_id={e.get('unique_id','')}")

# Check MQTT retained topics
print("\n--- MQTT Discovery Topics ---")
import paho.mqtt.client as mqtt
import time

mqtt_host = os.getenv("MQTT_HOST", "core-mosquitto")
if mqtt_host == "core-mosquitto":
    mqtt_host = "192.168.1.135"

topics_found = []

def on_message(client, userdata, message):
    if message.payload:
        payload = json.loads(message.payload.decode())
        topics_found.append((message.topic, payload.get("name",""), payload.get("unique_id",""), payload.get("object_id","")))

def on_connect(client, userdata, flags, rc, properties=None):
    client.subscribe("homeassistant/+/battery_manager/#")

client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
if os.getenv("MQTT_USER"):
    client.username_pw_set(os.getenv("MQTT_USER"), os.getenv("MQTT_PASSWORD"))
client.on_connect = on_connect
client.on_message = on_message
client.connect(mqtt_host, int(os.getenv("MQTT_PORT", 1883)), 60)
client.loop_start()
time.sleep(3)
client.loop_stop()
client.disconnect()

print(f"Found {len(topics_found)} retained discovery topics:\n")
for topic, name, uid, oid in sorted(topics_found):
    print(f"  topic={topic}")
    print(f"    name={name}  unique_id={uid}  object_id={oid}")
