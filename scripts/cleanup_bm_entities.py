#!/usr/bin/env python3
"""Cleanup all Battery Manager MQTT entities, HA entity registry, and device registry.

Run from repo root: python scripts/cleanup_bm_entities.py
"""

import json
import os
import shutil
import time
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

_raw_host = os.getenv("MQTT_HOST", "192.168.1.135")
MQTT_HOST = "192.168.1.135" if _raw_host == "core-mosquitto" else _raw_host
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_USER = os.getenv("MQTT_USER", "")
MQTT_PASSWORD = os.getenv("MQTT_PASSWORD", "")

HA_CONFIG_PATH = Path(r"\\192.168.1.135\config")
ENTITY_REGISTRY = HA_CONFIG_PATH / ".storage" / "core.entity_registry"
DEVICE_REGISTRY = HA_CONFIG_PATH / ".storage" / "core.device_registry"

ADDON_ID = "battery_manager"
DISCOVERY_PREFIX = "homeassistant"

# All entity object_ids (current + historical)
ENTITY_IDS = [
    "status", "reasoning", "forecast", "price_ranges",
    "current_action", "charge_schedule", "discharge_schedule",
    "schedule", "schedule_part_2", "mode",
    # Old bm_ prefixed
    "bm_status", "bm_reasoning", "bm_forecast", "bm_price_ranges",
    "bm_current_action", "bm_charge_schedule", "bm_discharge_schedule",
    "bm_schedule", "bm_schedule_2", "bm_mode",
]
# Double-prefixed variants
ENTITY_IDS += [f"battery_manager_{eid}" for eid in ENTITY_IDS[:10]]

COMPONENTS = ["sensor", "binary_sensor", "select", "number", "button", "text"]


def cleanup_mqtt():
    """Clear all retained MQTT discovery messages for battery_manager."""
    import paho.mqtt.client as mqtt

    print("=" * 60)
    print("Phase 1: MQTT Retained Message Cleanup")
    print("=" * 60)
    print(f"Broker: {MQTT_HOST}:{MQTT_PORT}")

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    if MQTT_USER:
        client.username_pw_set(MQTT_USER, MQTT_PASSWORD)

    connected = False
    def on_connect(c, ud, fl, rc, prop=None):
        nonlocal connected
        if rc == 0:
            print("  Connected to MQTT broker")
            connected = True

    client.on_connect = on_connect
    client.connect(MQTT_HOST, MQTT_PORT, 60)
    client.loop_start()
    for _ in range(50):
        if connected: break
        time.sleep(0.1)
    if not connected:
        print("  ERROR: Could not connect")
        return False

    count = 0
    for component in COMPONENTS:
        for eid in ENTITY_IDS:
            client.publish(f"{DISCOVERY_PREFIX}/{component}/{ADDON_ID}/{eid}/config", payload="", retain=True)
            count += 1
    for eid in ENTITY_IDS:
        for component in COMPONENTS:
            for suffix in ["state", "attributes", "set"]:
                client.publish(f"{ADDON_ID}/{component}/{eid}/{suffix}", payload="", retain=True)
                count += 1

    time.sleep(2)
    client.loop_stop()
    client.disconnect()
    print(f"  Cleared {count} retained MQTT topics")
    return True


def cleanup_entity_registry():
    """Remove battery_manager MQTT entities from HA entity registry."""
    print("\n" + "=" * 60)
    print("Phase 2: HA Entity Registry Cleanup")
    print("=" * 60)

    if not ENTITY_REGISTRY.exists():
        print(f"  WARNING: Not found: {ENTITY_REGISTRY}")
        return False

    backup = ENTITY_REGISTRY.with_suffix(f".backup_{datetime.now():%Y%m%d_%H%M%S}")
    shutil.copy2(ENTITY_REGISTRY, backup)
    print(f"  Backed up to: {backup.name}")

    with open(ENTITY_REGISTRY, "r") as f:
        data = json.load(f)

    entities = data["data"]["entities"]
    remaining, removed = [], []
    for e in entities:
        uid = str(e.get("unique_id", ""))
        if e.get("platform") == "mqtt" and "battery_manager" in uid:
            removed.append(e)
        else:
            remaining.append(e)

    for e in removed:
        print(f"  Removed: {e['entity_id']} (unique_id={e.get('unique_id','')})")

    data["data"]["entities"] = remaining
    with open(ENTITY_REGISTRY, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print(f"  Removed {len(removed)} entities ({len(entities)} -> {len(remaining)})")
    return True


def cleanup_device_registry():
    """Remove battery_manager MQTT device from HA device registry."""
    print("\n" + "=" * 60)
    print("Phase 3: HA Device Registry Cleanup")
    print("=" * 60)

    if not DEVICE_REGISTRY.exists():
        print(f"  WARNING: Not found: {DEVICE_REGISTRY}")
        return False

    backup = DEVICE_REGISTRY.with_suffix(f".backup_{datetime.now():%Y%m%d_%H%M%S}")
    shutil.copy2(DEVICE_REGISTRY, backup)
    print(f"  Backed up to: {backup.name}")

    with open(DEVICE_REGISTRY, "r") as f:
        data = json.load(f)

    devices = data["data"]["devices"]
    remaining, removed = [], []
    for d in devices:
        ids = str(d.get("identifiers", ""))
        if "mqtt" in ids and "battery_manager" in ids:
            removed.append(d)
        else:
            remaining.append(d)

    for d in removed:
        print(f"  Removed device: {d.get('name','')} (id={d.get('id','')})")

    data["data"]["devices"] = remaining
    with open(DEVICE_REGISTRY, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print(f"  Removed {len(removed)} devices ({len(devices)} -> {len(remaining)})")
    return True


def main():
    print(f"\nBattery Manager Entity Cleanup - {datetime.now():%Y-%m-%d %H:%M:%S}\n")
    s1 = cleanup_mqtt()
    s2 = cleanup_entity_registry()
    s3 = cleanup_device_registry()

    print("\n" + "=" * 60)
    print("ALL CLEANUP COMPLETE" if all([s1,s2,s3]) else "COMPLETED WITH WARNINGS")
    print("=" * 60)
    print("\nNext steps:")
    print("1. Restart Home Assistant Core")
    print("2. Update Battery Manager addon to new version")
    print("3. Start the addon - entities will be sensor.battery_manager_*")
    return 0


if __name__ == "__main__":
    exit(main())
