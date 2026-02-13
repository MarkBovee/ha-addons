#!/usr/bin/env python3
"""Inspect all .storage files for battery_manager remnants."""
import json
from pathlib import Path

config = Path(r"\\192.168.1.135\config\.storage")

# 1. Entity registry
print("=== Entity Registry ===")
data = json.loads((config / "core.entity_registry").read_text())
entities = data["data"]["entities"]
bm_mqtt = [e for e in entities if "battery_manager" in str(e.get("unique_id", "")) and e.get("platform") == "mqtt"]
bm_hassio = [e for e in entities if "battery_manager" in str(e.get("unique_id", "")) and e.get("platform") == "hassio"]
bm_old = [e for e in entities if "bm_" in str(e.get("unique_id", ""))]
for e in bm_mqtt:
    eid = e["entity_id"]
    uid = e.get("unique_id", "")
    print(f"  [MQTT]   {eid:50s} unique_id={uid}")
for e in bm_old:
    eid = e["entity_id"]
    uid = e.get("unique_id", "")
    print(f"  [OLD]    {eid:50s} unique_id={uid}")
for e in bm_hassio:
    eid = e["entity_id"]
    uid = e.get("unique_id", "")
    print(f"  [HASSIO] {eid:50s} unique_id={uid}")
if not bm_mqtt and not bm_old:
    print("  MQTT/old entries: CLEAN")
print(f"  Total: {len(bm_mqtt)} mqtt, {len(bm_old)} old bm_, {len(bm_hassio)} hassio")

# 2. Device registry
print("\n=== Device Registry ===")
data2 = json.loads((config / "core.device_registry").read_text())
devices = data2["data"]["devices"]
bm_dev = [d for d in devices if "battery_manager" in str(d.get("identifiers", ""))]
for d in bm_dev:
    name = d.get("name", "")
    did = d.get("id", "")
    ids = d.get("identifiers", "")
    print(f"  {name:30s} id={did[:20]} identifiers={ids}")
if not bm_dev:
    print("  CLEAN")

# 3. Restore state
print("\n=== Restore State ===")
data3 = json.loads((config / "core.restore_state").read_text(encoding="utf-8"))
# Structure varies by HA version
raw = data3.get("data", [])
if isinstance(raw, dict):
    state_list = raw.get("states", raw.get("entries", []))
else:
    state_list = raw if isinstance(raw, list) else []

bm_restore = []
for s in state_list:
    s_str = json.dumps(s)
    if "battery_manager" in s_str and "sensor." in s_str:
        eid = s.get("state", {}).get("entity_id", "") if isinstance(s, dict) else ""
        bm_restore.append(eid or s_str[:80])

print(f"  Found {len(bm_restore)} entries")
for entry in bm_restore:
    print(f"  - {entry}")

# 4. Lovelace
print("\n=== Lovelace ===")
print("  lovelace.battery_management is a dashboard config - keeping it")
