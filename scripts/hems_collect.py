#!/usr/bin/env python3
"""Read-only HEMS data collector.

Reads Home Assistant over REST (HA_API_URL + HA_API_TOKEN from .env or the
environment) and writes append-only JSONL files under
docs/hems/observations/data/:

  hourly.jsonl     one line per complete local hour: time-weighted mean/min/max
                   per numeric entity, state durations per categorical entity
  snapshots.jsonl  one line per run: current states of planning-related
                   entities (plans, schedules, limits, price-curve summary)

Never writes to Home Assistant. Safe to re-run: hours already present are skipped.

Usage:
  python3 scripts/hems_collect.py run [--hours 12]      # snapshot + hourly (cron/scheduled)
  python3 scripts/hems_collect.py hourly --hours 240    # backfill from recorder history
  python3 scripts/hems_collect.py snapshot
  python3 scripts/hems_collect.py dashboards            # lovelace configs (needs: pip install websockets)
"""
import argparse
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "hems" / "observations" / "data"
TZ = ZoneInfo("Europe/Amsterdam")

NUMERIC = [
    "sensor.battery_api_battery_soc", "sensor.battery_api_battery_power",
    "sensor.battery_api_pv_power", "sensor.battery_api_load_power", "sensor.battery_api_grid_power",
    "sensor.power_usage", "sensor.average_power_usage",
    "sensor.electricity_meter_power_consumption", "sensor.electricity_meter_power_production",
    "sensor.electricity_meter_voltage_phase_l1", "sensor.electricity_meter_voltage_phase_l2",
    "sensor.electricity_meter_voltage_phase_l3",
    "sensor.energy_prices_electricity_import_price", "sensor.energy_prices_electricity_export_price",
    "sensor.current_price",
    "sensor.saj_pv1_power", "sensor.saj_pv2_power", "sensor.energy_production_today_remaining",
    "sensor.ev4_ev_battery_level", "sensor.charge_amps_monitor_charger_current_power",
    "sensor.charge_amps_monitor_charger_current",
    "sensor.home_vaillant_arotherm_heat_pump_compressor_power",
    "sensor.home_vaillant_arotherm_heat_pump_compressor_speed",
    "sensor.home_vaillant_ctlv2_heating_control_displayed_outside_temp",
    "sensor.home_woonkamer_z1_room_temperature", "sensor.home_woonkamer_z1_flow_temperature_hc1",
    "sensor.wasmachine_huidig_gebruik", "sensor.droger_en_vriezer_huidig_gebruik",
    "sensor.tv_en_media_huidig_gebruik", "sensor.ems_huidig_gebruik",
    "sensor.computer_huidig_gebruik", "sensor.audio_huidig_gebruik", "sensor.garage_huidig_gebruik",
]
CATEGORICAL = [
    "sensor.battery_manager_current_action", "sensor.battery_manager_mode",
    "sensor.battery_api_schedule_status", "sensor.battery_api_api_status",
    "select.battery_api_battery_mode",
    "binary_sensor.charge_amps_monitor_charger_charging", "sensor.charge_amps_monitor_charger_status",
    "sensor.charge_amps_monitor_charging_schedule_status",
    "water_heater.home_boiler_dhw_domestic_hot_water", "input_text.heating_schedule_status",
    "sensor.home_vaillant_arotherm_heat_pump_compressor_status",
    "switch.ems", "climate.gree_climate", "sensor.vaatwasser_status", "switch.wasmachine",
]
SNAPSHOT_EXTRA = [
    "sensor.battery_manager_charge_schedule", "sensor.battery_manager_discharge_schedule",
    "sensor.battery_manager_schedule", "sensor.battery_manager_price_ranges",
    "sensor.battery_manager_reasoning", "sensor.battery_manager_effective_discharge_power",
    "number.saj_battery_charge_power_limit_input", "number.saj_battery_discharge_power_limit_input",
    "number.battery_api_export_limit", "number.saj_passive_battery_charge_power_input",
    "number.saj_passive_battery_discharge_power_input", "sensor.saj_battery_capacity",
    "sensor.charge_amps_monitor_next_charge_start", "sensor.charge_amps_monitor_next_charge_end",
]
SNAPSHOT_REGEX = re.compile(r"^sensor\.saj_(charge|discharge)_\d+_(start_time|end_time|power_percent|day_mask)$")
PRICE_CURVES = ["sensor.energy_prices_electricity_import_price", "sensor.energy_prices_electricity_export_price"]


def load_env():
    env = dict(os.environ)
    p = ROOT / ".env"
    if p.exists():
        for line in p.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env.setdefault(k.strip(), v.strip().strip("\"'"))
    return env


class Ha:
    def __init__(self, env):
        self.base = env["HA_API_URL"].rstrip("/")
        self.s = requests.Session()
        self.s.headers["Authorization"] = "Bearer " + env["HA_API_TOKEN"]

    def get(self, path, **params):
        r = self.s.get(self.base + path, params=params or None, timeout=60)
        r.raise_for_status()
        return r.json()


def parse_ts(ts):
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def price_summary(attrs, now):
    curve = attrs.get("price_curve") or []
    cur = None
    last_end = None
    for it in curve:
        s, e = parse_ts(it["start"]), parse_ts(it["end"])
        if s <= now < e:
            cur = it["price"]
        last_end = e if last_end is None or e > last_end else last_end
    tomorrow_start = (now.astimezone(TZ) + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return {
        "current_slot_price": cur, "slots": len(curve),
        "last_end_local": last_end.astimezone(TZ).isoformat() if last_end else None,
        "tomorrow_available": bool(last_end and last_end.astimezone(TZ) > tomorrow_start + timedelta(hours=1)),
        "percentiles": attrs.get("percentiles"), "last_update": attrs.get("last_update"),
    }


def snapshot(ha):
    now = datetime.now(timezone.utc)
    states = {s["entity_id"]: s for s in ha.get("/states")}
    wanted = NUMERIC + CATEGORICAL + SNAPSHOT_EXTRA
    row = {"ts_utc": now.isoformat(timespec="seconds"), "ts_local": now.astimezone(TZ).isoformat(timespec="seconds"),
           "states": {}, "price_curves": {}, "missing": []}
    for e in wanted:
        if e in states:
            row["states"][e] = states[e]["state"]
        else:
            row["missing"].append(e)
    for e, s in states.items():
        if SNAPSHOT_REGEX.match(e):
            row["states"][e] = s["state"]
    for e in PRICE_CURVES:
        if e in states:
            row["price_curves"][e] = price_summary(states[e]["attributes"], now)
    OUT.mkdir(parents=True, exist_ok=True)
    with open(OUT / "snapshots.jsonl", "a") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return row


def history(ha, entities, start, end):
    series = {}
    for i in range(0, len(entities), 20):
        chunk = entities[i:i + 20]
        data = ha.get("/history/period/" + start.isoformat(), filter_entity_id=",".join(chunk),
                      end_time=end.isoformat(), minimal_response="true", no_attributes="true",
                      significant_changes_only="0")
        for inner in data:
            if not inner:
                continue
            eid = inner[0].get("entity_id")
            series[eid] = [(parse_ts(x["last_changed"]), x["state"]) for x in inner]
    return series


def segments(series, h0, h1):
    segs, cur, cur_t = [], None, h0
    for t, s in series:
        if t <= h0:
            cur = s
            continue
        if t >= h1:
            break
        if cur is not None:
            segs.append((cur, (t - cur_t).total_seconds()))
        cur, cur_t = s, t
    if cur is not None:
        segs.append((cur, (h1 - cur_t).total_seconds()))
    return segs


def agg_numeric(segs):
    vals = [(num(s), d) for s, d in segs if num(s) is not None and d > 0]
    tot = sum(d for _, d in vals)
    if not tot:
        return {"mean": None, "min": None, "max": None, "last": None, "cov": 0}
    return {"mean": round(sum(v * d for v, d in vals) / tot, 4), "min": min(v for v, _ in vals),
            "max": max(v for v, _ in vals), "last": vals[-1][0], "cov": round(tot / 3600, 3)}


def agg_cat(segs):
    dur = {}
    for s, d in segs:
        dur[s] = dur.get(s, 0) + d
    return {"last": segs[-1][0] if segs else None, "dur": {k: round(v) for k, v in dur.items()}}


def hourly(ha, hours):
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / "hourly.jsonl"
    have = set()
    if path.exists():
        for line in path.read_text().splitlines():
            have.add(json.loads(line)["hour_utc"])
    end = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    todo = [end - timedelta(hours=h) for h in range(hours, 0, -1)]
    todo = [h for h in todo if h.isoformat(timespec="seconds") not in have]
    added = 0
    missing = set()
    for i in range(0, len(todo), 24):
        batch = todo[i:i + 24]
        w0, w1 = batch[0], batch[-1] + timedelta(hours=1)
        series = history(ha, NUMERIC + CATEGORICAL, w0, w1)
        missing.update(e for e in NUMERIC + CATEGORICAL if e not in series)
        with open(path, "a") as f:
            for h0 in batch:
                h1 = h0 + timedelta(hours=1)
                v = {}
                for e in NUMERIC:
                    if e in series:
                        v[e] = agg_numeric(segments(series[e], h0, h1))
                for e in CATEGORICAL:
                    if e in series:
                        v[e] = agg_cat(segments(series[e], h0, h1))
                f.write(json.dumps({"hour_utc": h0.isoformat(timespec="seconds"),
                                    "hour_local": h0.astimezone(TZ).isoformat(timespec="seconds"), "v": v},
                                   ensure_ascii=False) + "\n")
                added += 1
    return added, sorted(missing)


def dashboards(env):
    """Export all Lovelace dashboard configs over the websocket API (read-only)."""
    import asyncio
    import websockets

    base = env["HA_API_URL"].rstrip("/")
    ws_url = re.sub(r"^http", "ws", base) + "/websocket"
    stamp = datetime.now(TZ).strftime("%Y-%m-%d")
    outdir = OUT / "dashboards" / stamp
    outdir.mkdir(parents=True, exist_ok=True)

    async def run():
        async with websockets.connect(ws_url, max_size=None) as ws:
            await ws.recv()
            await ws.send(json.dumps({"type": "auth", "access_token": env["HA_API_TOKEN"]}))
            if json.loads(await ws.recv()).get("type") != "auth_ok":
                raise SystemExit("websocket auth failed")
            n = 0

            async def call(msg):
                nonlocal n
                n += 1
                await ws.send(json.dumps({"id": n, **msg}))
                while True:
                    r = json.loads(await ws.recv())
                    if r.get("id") == n:
                        return r

            listed = (await call({"type": "lovelace/dashboards/list"})).get("result", [])
            paths = [None] + [d["url_path"] for d in listed]
            saved = []
            for path in paths:
                msg = {"type": "lovelace/config", "force": True}
                if path:
                    msg["url_path"] = path
                r = await call(msg)
                if r.get("success"):
                    name = path or "lovelace"
                    (outdir / f"{name}.json").write_text(json.dumps(r["result"], indent=2, ensure_ascii=False, sort_keys=True))
                    saved.append(name)
            return saved

    saved = asyncio.run(run())
    print(f"dashboards saved to {outdir.relative_to(ROOT)}: {saved}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["run", "snapshot", "hourly", "dashboards"])
    ap.add_argument("--hours", type=int, default=12)
    a = ap.parse_args()
    env = load_env()
    if a.mode == "dashboards":
        return dashboards(env)
    ha = Ha(env)
    if a.mode in ("run", "snapshot"):
        row = snapshot(ha)
        print(f"snapshot {row['ts_local']}: {len(row['states'])} states, missing: {row['missing'] or 'none'}")
    if a.mode in ("run", "hourly"):
        added, missing = hourly(ha, a.hours)
        print(f"hourly: +{added} hours, no history for: {missing or 'none'}")


if __name__ == "__main__":
    sys.exit(main())
