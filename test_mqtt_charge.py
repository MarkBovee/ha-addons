#!/usr/bin/env python3
"""Send a test charge window to battery-api via MQTT.

Usage:
    python test_mqtt_charge.py                  # 500W for 30 min starting now
    python test_mqtt_charge.py --power 1000     # 1000W for 30 min
    python test_mqtt_charge.py --duration 60    # 500W for 60 min
    python test_mqtt_charge.py --start 14:30    # 500W for 30 min at 14:30
    python test_mqtt_charge.py --clear          # Clear schedule (empty)
"""

import argparse
import json
import time
from datetime import datetime, timezone

import paho.mqtt.client as mqtt

MQTT_HOST = "192.168.1.135"
MQTT_PORT = 1883
MQTT_USER = "mark"
MQTT_PASSWORD = "bovee"
TOPIC = "battery_api/text/schedule/set"


def main():
    parser = argparse.ArgumentParser(description="Send test charge schedule via MQTT")
    parser.add_argument("--power", type=int, default=500, help="Charge power in watts (default: 500)")
    parser.add_argument("--duration", type=int, default=30, help="Duration in minutes (default: 30)")
    parser.add_argument("--start", type=str, default=None, help="Start time HH:MM (default: now)")
    parser.add_argument("--clear", action="store_true", help="Send empty schedule to clear")
    parser.add_argument("--discharge", action="store_true", help="Send discharge instead of charge")
    args = parser.parse_args()

    if args.clear:
        schedule = {"charge": [], "discharge": []}
    else:
        start_time = args.start
        if not start_time:
            now = datetime.now()
            start_time = now.strftime("%H:%M")

        period = {
            "start": start_time,
            "power": args.power,
            "duration": args.duration,
        }

        if args.discharge:
            schedule = {"charge": [], "discharge": [period]}
        else:
            schedule = {"charge": [period], "discharge": []}

    payload = json.dumps(schedule)

    print(f"Connecting to MQTT {MQTT_HOST}:{MQTT_PORT}...")
    client = mqtt.Client(client_id="test_charge_sender")
    client.username_pw_set(MQTT_USER, MQTT_PASSWORD)

    connected = False

    def on_connect(c, userdata, flags, rc):
        nonlocal connected
        if rc == 0:
            connected = True
            print("Connected to MQTT broker")
        else:
            print(f"Connection failed with code {rc}")

    client.on_connect = on_connect
    client.connect(MQTT_HOST, MQTT_PORT, 60)
    client.loop_start()

    # Wait for connection
    for _ in range(50):
        if connected:
            break
        time.sleep(0.1)

    if not connected:
        print("ERROR: Could not connect to MQTT broker")
        client.loop_stop()
        return

    print(f"Publishing to: {TOPIC}")
    print(f"Payload: {payload}")
    result = client.publish(TOPIC, payload, qos=1)
    result.wait_for_publish()
    print(f"Published successfully (mid={result.mid})")

    client.loop_stop()
    client.disconnect()
    print("Done. Check battery-api logs for schedule reception.")


if __name__ == "__main__":
    main()
