#!/usr/bin/env python3
"""Test script to read schedule, increase discharge by 400W, and write back.

Usage:
    python test_schedule.py [--dry-run]
    
Requires HA_API_URL, HA_API_TOKEN, and MQTT credentials in .env file.
"""

import json
import os
import sys
import argparse
import time
from dotenv import load_dotenv
import requests
import paho.mqtt.client as mqtt

# Load .env file from current directory or parent
load_dotenv()
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

HA_API_URL = os.getenv('HA_API_URL', 'http://supervisor/core').rstrip('/')
# Remove /api suffix if present (we add it in the calls)
if HA_API_URL.endswith('/api'):
    HA_API_URL = HA_API_URL[:-4]
HA_API_TOKEN = os.getenv('HA_API_TOKEN') or os.getenv('SUPERVISOR_TOKEN')

# MQTT settings
MQTT_HOST = os.getenv('MQTT_HOST', '192.168.1.135')
MQTT_PORT = int(os.getenv('MQTT_PORT', '1883'))
MQTT_USER = os.getenv('MQTT_USER', '')
MQTT_PASSWORD = os.getenv('MQTT_PASSWORD', '')

# Topic the add-on listens to for schedule commands
SCHEDULE_COMMAND_TOPIC = "battery_api/text/schedule/set"


def get_ha_headers():
    """Get headers for HA API calls."""
    if not HA_API_TOKEN:
        raise ValueError("HA_API_TOKEN or SUPERVISOR_TOKEN not set")
    return {
        "Authorization": f"Bearer {HA_API_TOKEN}",
        "Content-Type": "application/json",
    }


def get_current_schedule_from_saj() -> dict:
    """Get current schedule from SAJ API via the add-on's sensor.
    
    The add-on fetches and publishes the current schedule from the inverter
    to a sensor attribute or separate sensor.
    """
    # For now, return empty - we'll use a default test schedule
    # In production, this would read from sensor.battery_api_current_schedule
    return {}


def set_schedule_via_mqtt(schedule: dict, dry_run: bool = False) -> bool:
    """Set schedule by publishing to MQTT command topic.
    
    The add-on subscribes to battery_api/text/schedule/set and applies
    the schedule when a message is received.
    """
    json_str = json.dumps(schedule)
    
    print(f"\nNew schedule JSON:\n{json.dumps(schedule, indent=2)}")
    
    if dry_run:
        print("\n[DRY RUN] Would publish schedule to MQTT")
        return True
    
    print(f"\nPublishing to MQTT topic: {SCHEDULE_COMMAND_TOPIC}")
    print(f"MQTT Broker: {MQTT_HOST}:{MQTT_PORT}")
    
    connected = False
    def on_connect(client, userdata, flags, rc, props=None):
        nonlocal connected
        if rc == 0 or (hasattr(rc, 'is_failure') and not rc.is_failure):
            connected = True
        else:
            print(f"MQTT connect failed: {rc}")
    
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    if MQTT_USER:
        client.username_pw_set(MQTT_USER, MQTT_PASSWORD)
    client.on_connect = on_connect
    
    try:
        client.connect(MQTT_HOST, MQTT_PORT, 60)
        client.loop_start()
        
        # Wait for connection
        for _ in range(50):
            if connected:
                break
            time.sleep(0.1)
        
        if not connected:
            print("✗ Failed to connect to MQTT broker")
            return False
        
        print("✓ Connected to MQTT")
        
        # Publish schedule to command topic
        result = client.publish(SCHEDULE_COMMAND_TOPIC, json_str)
        result.wait_for_publish()
        
        print(f"✓ Published schedule to {SCHEDULE_COMMAND_TOPIC}")
        
        time.sleep(1)  # Give add-on time to process
        return True
        
    except Exception as e:
        print(f"✗ MQTT error: {e}")
        return False
    finally:
        client.loop_stop()
        client.disconnect()


def main():
    parser = argparse.ArgumentParser(description="Test schedule modification")
    parser.add_argument('--dry-run', action='store_true', help="Don't actually write")
    parser.add_argument('--increase', type=int, default=400, help="Amount to increase discharge power (default: 400)")
    args = parser.parse_args()
    
    print("=" * 60)
    print("Battery Schedule Test (via MQTT)")
    print("=" * 60)
    print(f"MQTT Broker: {MQTT_HOST}:{MQTT_PORT}")
    print(f"Command Topic: {SCHEDULE_COMMAND_TOPIC}")
    print()
    
    # Step 1: Create a test schedule (or get from SAJ API in future)
    print("Step 1: Creating test schedule...")
    schedule = {
        "charge": [],
        "discharge": [
            {"start": "17:00", "power": 2500, "duration": 120}
        ]
    }
    
    print(f"\nBase schedule:")
    print(f"  Charge periods: {len(schedule.get('charge', []))}")
    for i, p in enumerate(schedule.get('charge', [])):
        print(f"    [{i}] {p['start']} - {p['power']}W for {p['duration']} min")
    print(f"  Discharge periods: {len(schedule.get('discharge', []))}")
    for i, p in enumerate(schedule.get('discharge', [])):
        print(f"    [{i}] {p['start']} - {p['power']}W for {p['duration']} min")
    
    # Step 2: Modify discharge power
    print(f"\nStep 2: Increasing discharge power by {args.increase}W...")
    
    discharge = schedule.get('discharge', [])
    for p in discharge:
        old_power = p['power']
        p['power'] = old_power + args.increase
        print(f"  {p['start']}: {old_power}W -> {p['power']}W")
    
    schedule['discharge'] = discharge
    
    # Step 3: Write via MQTT
    print(f"\nStep 3: Sending schedule via MQTT...")
    success = set_schedule_via_mqtt(schedule, dry_run=args.dry_run)
    
    if success:
        print("\n" + "=" * 60)
        print("✓ Schedule sent successfully!")
        print("=" * 60)
        if not args.dry_run:
            print("\nCheck add-on logs for:")
            print("  - 'SCHEDULE INPUT RECEIVED' banner")
            print("  - 'Validated: 0 charge, 1 discharge periods'")
            print("  - 'Applying 1 periods to inverter'")
    else:
        print("\n✗ Failed to update schedule")
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
