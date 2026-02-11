#!/usr/bin/env python3
"""Read all battery manager entities from HA."""
import os, json, requests
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(Path(__file__).parent / ".env")

token = os.getenv("HA_API_TOKEN")
base = os.getenv("HA_API_URL")
h = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

# Find all bm_ entities
resp = requests.get(f"{base}/states", headers=h, timeout=10)
states = resp.json()
bm = [s for s in states if s["entity_id"].startswith("sensor.bm_")]

if not bm:
    print("No sensor.bm_* entities found!")
    # Check for battery_manager entities
    bm2 = [s for s in states if "battery_manager" in s["entity_id"]]
    if bm2:
        print(f"\nFound {len(bm2)} battery_manager entities instead:")
        for s in bm2:
            print(f"  {s['entity_id']}")
        bm = bm2

print(f"\nFound {len(bm)} entities:\n")
for s in bm:
    print("=" * 80)
    print(f"Entity: {s['entity_id']}")
    print(f"State:  {s['state']}")
    attrs = {k: v for k, v in s["attributes"].items()
             if k not in ["friendly_name", "icon", "device_class", "unit_of_measurement"]}
    if attrs:
        print(f"Attrs:  {json.dumps(attrs, indent=2, default=str)}")
    print()

# Also fetch the price curves to compare
print("\n" + "=" * 80)
print("PRICE CURVE DATA (for comparison)")
print("=" * 80)
for eid in ["sensor.energy_prices_electricity_import_price",
            "sensor.energy_prices_electricity_export_price"]:
    resp2 = requests.get(f"{base}/states/{eid}", headers=h, timeout=10)
    if resp2.status_code == 200:
        data = resp2.json()
        print(f"\n{eid}")
        print(f"  State: {data['state']}")
        attrs = data.get("attributes", {})
        curve = attrs.get("price_curve") or attrs.get("prices") or attrs.get("forecast")
        if curve:
            print(f"  Price curve ({len(curve)} points):")
            for p in curve[:30]:
                print(f"    {p}")
        else:
            # Print all attribute keys
            print(f"  Attr keys: {list(attrs.keys())}")
    else:
        print(f"\n{eid}: status {resp2.status_code}")

# SOC
resp3 = requests.get(f"{base}/states/sensor.battery_api_battery_soc", headers=h, timeout=10)
if resp3.status_code == 200:
    print(f"\nSOC: {resp3.json()['state']}%")
