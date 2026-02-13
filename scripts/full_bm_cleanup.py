#!/usr/bin/env python3
"""Remove all battery_manager remnants from HA .storage files.

Cleans:
- Entity registry: MQTT battery_manager entries + hassio entries (addon uninstalled)
- Device registry: Both MQTT and hassio battery_manager devices
- Restore state: All battery_manager cached states
- MQTT retained discovery topics
"""
import json
import os
import shutil
import time
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

config = Path(r"\\192.168.1.135\config\.storage")


def backup_and_load(filename):
    filepath = config / filename
    backup = filepath.with_suffix(f".pre_cleanup_{datetime.now():%H%M%S}")
    shutil.copy2(filepath, backup)
    data = json.loads(filepath.read_text(encoding="utf-8"))
    return filepath, data, backup.name


def clean_entity_registry():
    print("=== Entity Registry ===")
    filepath, data, bkp = backup_and_load("core.entity_registry")
    entities = data["data"]["entities"]
    before = len(entities)

    remaining = []
    removed = []
    for e in entities:
        uid = str(e.get("unique_id", ""))
        platform = e.get("platform", "")
        # Remove MQTT battery_manager entities
        if platform == "mqtt" and "battery_manager" in uid:
            removed.append(e)
        # Remove hassio battery_manager entities (addon is uninstalled)
        elif platform == "hassio" and "battery_manager" in uid:
            removed.append(e)
        # Remove old bm_ prefixed
        elif platform == "mqtt" and uid.startswith("bm_"):
            removed.append(e)
        else:
            remaining.append(e)

    for e in removed:
        print(f"  Removed: {e['entity_id']} ({e.get('platform','')}, uid={e.get('unique_id','')})")

    data["data"]["entities"] = remaining
    filepath.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"  Removed {len(removed)} entries ({before} -> {len(remaining)}), backup: {bkp}")


def clean_device_registry():
    print("\n=== Device Registry ===")
    filepath, data, bkp = backup_and_load("core.device_registry")
    devices = data["data"]["devices"]
    before = len(devices)

    remaining = []
    removed = []
    for d in devices:
        ids = str(d.get("identifiers", ""))
        if "battery_manager" in ids:
            removed.append(d)
        else:
            remaining.append(d)

    for d in removed:
        name = d.get("name", "")
        identifiers = d.get("identifiers", "")
        print(f"  Removed: {name} ({identifiers})")

    data["data"]["devices"] = remaining
    filepath.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"  Removed {len(removed)} devices ({before} -> {len(remaining)}), backup: {bkp}")


def clean_restore_state():
    print("\n=== Restore State ===")
    filepath, data, bkp = backup_and_load("core.restore_state")

    # Navigate the structure - varies by HA version
    raw = data.get("data", [])
    if isinstance(raw, dict):
        state_list = raw.get("states", raw.get("entries", []))
        key = "states" if "states" in raw else "entries"
    else:
        state_list = raw if isinstance(raw, list) else []
        key = None

    before = len(state_list)
    remaining = []
    removed_count = 0

    for s in state_list:
        s_str = json.dumps(s)
        if "battery_manager" in s_str:
            removed_count += 1
            eid = ""
            if isinstance(s, dict):
                eid = s.get("state", {}).get("entity_id", "")
            print(f"  Removed: {eid or s_str[:60]}")
        else:
            remaining.append(s)

    if key and isinstance(raw, dict):
        raw[key] = remaining
    elif isinstance(data.get("data"), list):
        data["data"] = remaining

    filepath.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"  Removed {removed_count} entries ({before} -> {len(remaining)}), backup: {bkp}")


def clean_mqtt():
    print("\n=== MQTT Retained Topics ===")
    import paho.mqtt.client as mqtt

    mqtt_host = os.getenv("MQTT_HOST", "core-mosquitto")
    if mqtt_host == "core-mosquitto":
        mqtt_host = "192.168.1.135"
    mqtt_port = int(os.getenv("MQTT_PORT", "1883"))

    # Collect all retained battery_manager topics
    found_topics = []

    def on_message(client, userdata, message):
        if message.payload and message.retain:
            found_topics.append(message.topic)

    def on_connect(client, userdata, flags, rc, properties=None):
        # Subscribe to all possible battery_manager topics
        client.subscribe("homeassistant/+/battery_manager/#")
        client.subscribe("battery_manager/#")

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    if os.getenv("MQTT_USER"):
        client.username_pw_set(os.getenv("MQTT_USER"), os.getenv("MQTT_PASSWORD"))
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(mqtt_host, mqtt_port, 60)
    client.loop_start()
    time.sleep(3)

    print(f"  Found {len(found_topics)} retained topics")
    for t in sorted(found_topics):
        print(f"  Clearing: {t}")
        client.publish(t, payload="", retain=True)

    if not found_topics:
        print("  CLEAN - no retained topics found")

    time.sleep(1)
    client.loop_stop()
    client.disconnect()


def main():
    print(f"Battery Manager Full Cleanup - {datetime.now():%Y-%m-%d %H:%M:%S}\n")
    clean_entity_registry()
    clean_device_registry()
    clean_restore_state()
    clean_mqtt()
    print("\n" + "=" * 60)
    print("DONE - Ready for HA restart")
    print("=" * 60)


if __name__ == "__main__":
    main()
