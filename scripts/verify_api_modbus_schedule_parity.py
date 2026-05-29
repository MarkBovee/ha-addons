#!/usr/bin/env python3
"""Verify schedule parity between SAJ cloud API and HA Modbus backend.

Default mode is read-only: load both backends, compare current schedules, and
propose a small reversible Modbus change.

Use `--execute` to:
1. back up the current API schedule and mode
2. apply a small schedule change through the Modbus backend
3. poll the SAJ cloud API until it sees the same normalized change
4. restore the original schedule and mode

Examples:
    python scripts/verify_api_modbus_schedule_parity.py
    python scripts/verify_api_modbus_schedule_parity.py --execute
    python scripts/verify_api_modbus_schedule_parity.py --execute --clear-test
    python scripts/verify_api_modbus_schedule_parity.py --execute --allow-create
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


ROOT = Path(__file__).resolve().parents[1]
BATTERY_API_DIR = ROOT / "battery-api"

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(BATTERY_API_DIR))

from app.backends import ApiBatteryBackend, BackendContext, ModbusHaBatteryBackend  # noqa: E402
from app.models import BatteryChargeType, ChargingPeriod  # noqa: E402


SELECT_TO_CANONICAL_MODE = {
    "self-consumption": "self-consumption",
    "time-of-use": "time-of-use",
    "ai": "ai",
}

CANONICAL_TO_SELECT_MODE = {
    "self-consumption": "Self-consumption",
    "time-of-use": "Time-of-use",
    "ai": "AI",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify SAJ API <-> Modbus schedule parity",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Apply Modbus write, verify through API, then restore original schedule",
    )
    parser.add_argument(
        "--allow-create",
        action="store_true",
        help="Create a temporary schedule when no baseline schedule exists",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Continue even when current API and Modbus schedules do not match",
    )
    parser.add_argument(
        "--clear-test",
        action="store_true",
        help="Verify Modbus schedule clear -> API read-back -> restore original schedule",
    )
    parser.add_argument(
        "--power-tolerance-w",
        type=int,
        default=250,
        help="Allowed API/Modbus power delta when comparing normalized schedules",
    )
    parser.add_argument(
        "--poll-attempts",
        type=int,
        default=12,
        help="Max cloud-API read-back attempts after write or restore",
    )
    parser.add_argument(
        "--poll-interval-seconds",
        type=float,
        default=10.0,
        help="Delay between cloud-API read-back attempts",
    )
    parser.add_argument(
        "--inverter-power-w",
        type=int,
        default=8000,
        help="Modbus watts-to-percent reference power",
    )
    return parser.parse_args()


def load_env_file(path: Path) -> Dict[str, str]:
    env: Dict[str, str] = {}
    if not path.exists():
        return env

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip().rstrip("\r")
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        env[key.strip()] = value.strip().strip("\"'")
    return env


def apply_env() -> List[Path]:
    loaded_paths: List[Path] = []
    merged: Dict[str, str] = {}
    for path in (ROOT / ".env", BATTERY_API_DIR / ".env"):
        if path.exists():
            merged.update(load_env_file(path))
            loaded_paths.append(path)

    for key, value in merged.items():
        os.environ[key] = value

    ha = os.environ.get("HA_API_TOKEN")
    supervisor = os.environ.get("SUPERVISOR_TOKEN")
    if ha and not supervisor:
        os.environ["SUPERVISOR_TOKEN"] = ha
    if supervisor and not ha:
        os.environ["HA_API_TOKEN"] = supervisor

    return loaded_paths


def canonical_mode(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    normalized = str(value).strip().lower().replace("_", "-")
    if normalized in ("self-consumption", "selfconsumption", "0"):
        return "self-consumption"
    if normalized in ("time-of-use", "timeofuse", "tou", "1"):
        return "time-of-use"
    if normalized in ("ai", "ai-mode", "aimode", "12"):
        return "ai"
    if normalized in SELECT_TO_CANONICAL_MODE:
        return SELECT_TO_CANONICAL_MODE[normalized]
    return normalized


def strip_mode(schedule: Dict[str, Any]) -> Dict[str, List[Dict[str, int | str]]]:
    return {
        "charge": normalize_periods(schedule.get("charge") or []),
        "discharge": normalize_periods(schedule.get("discharge") or []),
    }


def normalize_periods(periods: List[Dict[str, Any]]) -> List[Dict[str, int | str]]:
    normalized: List[Dict[str, int | str]] = []
    for period in periods:
        normalized.append(
            {
                "start": str(period["start"]),
                "duration": int(period["duration"]),
                "power": int(period["power"]),
            }
        )
    return sorted(normalized, key=lambda item: (str(item["start"]), int(item["duration"]), int(item["power"])))


def normalized_schedule(schedule: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "mode": canonical_mode(schedule.get("mode")),
        "charge": normalize_periods(schedule.get("charge") or []),
        "discharge": normalize_periods(schedule.get("discharge") or []),
    }


def schedule_has_periods(schedule: Dict[str, Any]) -> bool:
    return bool(schedule.get("charge") or schedule.get("discharge"))


def parse_hhmm(value: str) -> int:
    hour = int(value[:2])
    minute = int(value[3:])
    return hour * 60 + minute


def format_hhmm(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def shift_hhmm(value: str, delta_minutes: int) -> Optional[str]:
    shifted = parse_hhmm(value) + delta_minutes
    if shifted < 0 or shifted > 23 * 60 + 59:
        return None
    return format_hhmm(shifted)


def period_bounds(period: Dict[str, Any]) -> Tuple[int, int]:
    start = parse_hhmm(str(period["start"]))
    end = start + int(period["duration"])
    return start, end


def validate_schedule_shape(schedule: Dict[str, Any]) -> Optional[str]:
    combined: List[Tuple[str, int, int, str]] = []
    for bucket in ("charge", "discharge"):
        periods = schedule.get(bucket) or []
        if len(periods) > 7:
            return f"{bucket} exceeds 7 slots"
        for index, period in enumerate(periods):
            start = str(period["start"])
            if len(start) != 5 or start[2] != ":":
                return f"{bucket}[{index}] invalid time format"
            try:
                start_minutes, end_minutes = period_bounds(period)
            except Exception as exc:  # pragma: no cover - defensive
                return f"{bucket}[{index}] invalid time values: {exc}"
            power = int(period["power"])
            duration = int(period["duration"])
            if duration < 0 or duration > 1439:
                return f"{bucket}[{index}] invalid duration"
            if power < 0 or power > 10000:
                return f"{bucket}[{index}] invalid power"
            if end_minutes > 23 * 60 + 59:
                return f"{bucket}[{index}] crosses midnight"
            combined.append((bucket, start_minutes, end_minutes, f"{bucket}[{index}]"))

    for index, first in enumerate(combined):
        for second in combined[index + 1 :]:
            _, start1, end1, label1 = first
            _, start2, end2, label2 = second
            if start1 < end2 and start2 < end1:
                return f"{label1} overlaps {label2}"
    return None


def watts_to_percent(power_w: int, inverter_power_w: int) -> int:
    percent = round((max(0, power_w) / float(inverter_power_w)) * 100)
    return max(0, min(100, int(percent)))


def percent_to_watts(percent: int, inverter_power_w: int) -> int:
    return int(round((max(0, percent) / 100.0) * inverter_power_w))


def build_test_schedule(inverter_power_w: int) -> Dict[str, List[Dict[str, int | str]]]:
    start_dt = datetime.now() + timedelta(hours=2)
    rounded_minutes = ((start_dt.hour * 60 + start_dt.minute + 14) // 15) * 15
    if rounded_minutes + 15 > 23 * 60 + 59:
        raise RuntimeError("No safe future slot left today; rerun earlier or use an existing schedule")

    return {
        "charge": [
            {
                "start": format_hhmm(rounded_minutes),
                "duration": 15,
                "power": percent_to_watts(10, inverter_power_w),
            }
        ],
        "discharge": [],
    }


def derive_candidate_schedule(
    baseline_schedule: Dict[str, Any],
    inverter_power_w: int,
    allow_create: bool,
) -> Tuple[Dict[str, List[Dict[str, int | str]]], str]:
    baseline = strip_mode(baseline_schedule)
    if not schedule_has_periods(baseline):
        if not allow_create:
            raise RuntimeError("No current schedule found. Re-run with --allow-create to create a temporary test slot")
        candidate = build_test_schedule(inverter_power_w)
        return candidate, "Created temporary charge slot for parity test"

    for bucket in ("charge", "discharge"):
        for index, period in enumerate(baseline[bucket]):
            for delta_minutes in (1, -1, 2, -2, 5, -5, 15, -15):
                new_start = shift_hhmm(str(period["start"]), delta_minutes)
                if not new_start or new_start == period["start"]:
                    continue
                candidate = copy.deepcopy(baseline)
                candidate[bucket][index]["start"] = new_start
                error = validate_schedule_shape(candidate)
                if not error:
                    return candidate, f"Shifted {bucket}[{index}] start {period['start']} -> {new_start}"

            current_duration = int(period["duration"])
            for delta_duration in (1, -1, 2, -2, 5, -5):
                new_duration = current_duration + delta_duration
                if new_duration <= 0 or new_duration > 1439:
                    continue
                candidate = copy.deepcopy(baseline)
                candidate[bucket][index]["duration"] = new_duration
                error = validate_schedule_shape(candidate)
                if not error:
                    return (
                        candidate,
                        f"Adjusted {bucket}[{index}] duration {current_duration}m -> {new_duration}m",
                    )

    raise RuntimeError("Could not derive a small reversible schedule mutation")


def compare_schedules(
    actual: Dict[str, Any],
    expected: Dict[str, Any],
    power_tolerance_w: int,
    compare_mode: bool = True,
) -> List[str]:
    diffs: List[str] = []
    actual_normalized = normalized_schedule(actual)
    expected_normalized = normalized_schedule(expected)

    if compare_mode and actual_normalized.get("mode") != expected_normalized.get("mode"):
        diffs.append(
            f"mode mismatch: expected {expected_normalized.get('mode')}, got {actual_normalized.get('mode')}"
        )

    for bucket in ("charge", "discharge"):
        actual_items = actual_normalized[bucket]
        expected_items = expected_normalized[bucket]
        if len(actual_items) != len(expected_items):
            diffs.append(f"{bucket} count mismatch: expected {len(expected_items)}, got {len(actual_items)}")
            continue

        for index, (actual_item, expected_item) in enumerate(zip(actual_items, expected_items)):
            if actual_item["start"] != expected_item["start"]:
                diffs.append(
                    f"{bucket}[{index}] start mismatch: expected {expected_item['start']}, got {actual_item['start']}"
                )
            if actual_item["duration"] != expected_item["duration"]:
                diffs.append(
                    f"{bucket}[{index}] duration mismatch: expected {expected_item['duration']}, got {actual_item['duration']}"
                )
            power_delta = abs(int(actual_item["power"]) - int(expected_item["power"]))
            if power_delta > power_tolerance_w:
                diffs.append(
                    f"{bucket}[{index}] power mismatch: expected {expected_item['power']}, got {actual_item['power']}"
                )

    return diffs


def build_backend_context(config: Dict[str, Any]) -> BackendContext:
    return BackendContext(
        config=config,
        status={"api_status": "Initializing"},
        simulation_mode=False,
        battery_mode_setting="Self-consumption",
        schedule_json="{}",
        validated_schedule=None,
    )


def build_api_backend() -> Tuple[ApiBatteryBackend, BackendContext]:
    config = {
        "provider": "api",
        "saj_username": os.getenv("SAJ_USERNAME", ""),
        "saj_password": os.getenv("SAJ_PASSWORD", ""),
        "device_serial_number": os.getenv("SAJ_DEVICE_SERIAL", ""),
        "plant_uid": os.getenv("SAJ_PLANT_UID", ""),
    }
    missing = [key for key, value in config.items() if key != "provider" and not value]
    if missing:
        raise RuntimeError(f"Missing API env values: {', '.join(missing)}")

    context = build_backend_context(config)
    backend = ApiBatteryBackend(context)
    if not backend.setup():
        raise RuntimeError(f"API backend setup failed: {context.status.get('api_status')}")
    return backend, context


def build_modbus_backend(inverter_power_w: int) -> Tuple[ModbusHaBatteryBackend, BackendContext]:
    config = {
        "provider": "modbus_ha",
        "modbus_inverter_power_w": inverter_power_w,
        "modbus_entities": {},
    }
    context = build_backend_context(config)
    backend = ModbusHaBatteryBackend(context)
    if not backend.setup():
        raise RuntimeError(f"Modbus backend setup failed: {context.status.get('api_status')}")
    return backend, context


def fetch_api_schedule(api_backend: ApiBatteryBackend) -> Dict[str, Any]:
    schedule = api_backend.client.get_schedule() or {}
    return {
        "mode": schedule.get("mode"),
        "charge": normalize_periods(schedule.get("charge") or []),
        "discharge": normalize_periods(schedule.get("discharge") or []),
    }


def fetch_modbus_schedule(modbus_backend: ModbusHaBatteryBackend, context: BackendContext) -> Dict[str, Any]:
    context.schedule_json = "{}"
    modbus_backend.fetch_current_schedule()
    schedule = json.loads(context.status.get("current_schedule") or "{}")
    return {
        "mode": canonical_mode(context.battery_mode_setting),
        "charge": normalize_periods(schedule.get("charge") or []),
        "discharge": normalize_periods(schedule.get("discharge") or []),
    }


def pretty_json(value: Dict[str, Any]) -> str:
    return json.dumps(value, indent=2, sort_keys=True)


def dump_modbus_entities(modbus_backend: ModbusHaBatteryBackend, label: str) -> None:
    interesting_keys = [
        "app_mode",
        "app_mode_input",
        "charge_time_enable",
        "charge_time_enable_input",
        "charge1_start_time",
        "charge1_end_time",
        "charge1_power_percent",
        "charge1_day_mask",
        "charge1_start_time_input",
        "charge1_end_time_input",
        "charge1_power_percent_input",
        "charge1_day_mask_input",
        "discharge_time_enable",
        "discharge_time_enable_input",
        "discharge1_start_time",
        "discharge1_end_time",
        "discharge1_power_percent",
        "discharge1_day_mask",
        "discharge1_start_time_input",
        "discharge1_end_time_input",
        "discharge1_power_percent_input",
        "discharge1_day_mask_input",
    ]

    snapshot: Dict[str, Dict[str, Any]] = {}
    for key in interesting_keys:
        entity_id = modbus_backend.entities.get(key)
        if not entity_id:
            continue
        state = modbus_backend.ha_api.get_entity_state(entity_id)
        snapshot[key] = {
            "entity_id": entity_id,
            "state": None if not state else state.get("state"),
            "attributes": {} if not state else state.get("attributes", {}),
        }

    print(f"\n{label}:")
    print(json.dumps(snapshot, indent=2, sort_keys=True))


def force_refresh_modbus_entities(modbus_backend: ModbusHaBatteryBackend) -> None:
    refresh_keys = [
        "app_mode",
        "charge_time_enable",
        "charge1_start_time",
        "charge1_end_time",
        "charge1_power_percent",
        "discharge_time_enable",
        "discharge1_start_time",
        "discharge1_end_time",
        "discharge1_power_percent",
    ]
    for key in refresh_keys:
        entity_id = modbus_backend.entities.get(key)
        if not entity_id:
            continue
        modbus_backend.ha_api.call_service("homeassistant", "update_entity", {"entity_id": entity_id})


def expected_mode_for_schedule(schedule: Dict[str, Any]) -> str:
    return "time-of-use" if schedule_has_periods(schedule) else "self-consumption"


def apply_modbus_schedule(modbus_backend: ModbusHaBatteryBackend, schedule: Dict[str, Any]) -> None:
    payload = json.dumps(strip_mode(schedule))
    if not modbus_backend.save_schedule([], payload):
        raise RuntimeError(modbus_backend.context.status.get("schedule_status") or "Modbus save failed")


def restore_modbus_state(modbus_backend: ModbusHaBatteryBackend, original_schedule: Dict[str, Any]) -> None:
    apply_modbus_schedule(modbus_backend, original_schedule)
    original_mode = canonical_mode(original_schedule.get("mode"))
    if original_mode and original_mode != expected_mode_for_schedule(original_schedule):
        target = CANONICAL_TO_SELECT_MODE.get(original_mode)
        if not target:
            raise RuntimeError(f"Cannot restore unsupported mode {original_mode}")
        if not modbus_backend.set_mode(target):
            raise RuntimeError(modbus_backend.context.status.get("api_status") or "Mode restore failed")


def wait_for_api_schedule(
    api_backend: ApiBatteryBackend,
    expected_schedule: Dict[str, Any],
    power_tolerance_w: int,
    attempts: int,
    interval_seconds: float,
) -> Tuple[Dict[str, Any], List[str], int]:
    last_actual: Dict[str, Any] = {}
    last_diffs: List[str] = ["no API response yet"]
    for attempt in range(1, attempts + 1):
        last_actual = fetch_api_schedule(api_backend)
        last_diffs = compare_schedules(last_actual, expected_schedule, power_tolerance_w)
        if not last_diffs:
            return last_actual, [], attempt
        if attempt < attempts:
            time.sleep(interval_seconds)
    return last_actual, last_diffs, attempts


def wait_for_modbus_schedule(
    modbus_backend: ModbusHaBatteryBackend,
    modbus_context: BackendContext,
    expected_schedule: Dict[str, Any],
    power_tolerance_w: int,
    attempts: int,
    interval_seconds: float,
) -> Tuple[Dict[str, Any], List[str], int]:
    last_actual: Dict[str, Any] = {}
    last_diffs: List[str] = ["no Modbus response yet"]
    for attempt in range(1, attempts + 1):
        force_refresh_modbus_entities(modbus_backend)
        time.sleep(interval_seconds)
        last_actual = fetch_modbus_schedule(modbus_backend, modbus_context)
        last_diffs = compare_schedules(last_actual, expected_schedule, power_tolerance_w)
        if not last_diffs:
            return last_actual, [], attempt
    return last_actual, last_diffs, attempts


def main() -> int:
    args = parse_args()
    loaded_paths = apply_env()

    print("Loaded env:")
    for path in loaded_paths:
        print(f"- {path}")

    api_backend, _api_context = build_api_backend()
    modbus_backend, modbus_context = build_modbus_backend(args.inverter_power_w)

    baseline_api = fetch_api_schedule(api_backend)
    baseline_modbus = fetch_modbus_schedule(modbus_backend, modbus_context)

    print("\nCurrent API schedule:")
    print(pretty_json(baseline_api))
    print("\nCurrent Modbus schedule:")
    print(pretty_json(baseline_modbus))

    baseline_diffs = compare_schedules(
        baseline_modbus,
        baseline_api,
        power_tolerance_w=args.power_tolerance_w,
        compare_mode=True,
    )
    if baseline_diffs:
        print("\nCurrent API/Modbus mismatch:")
        for diff in baseline_diffs:
            print(f"- {diff}")
        if not args.force:
            print("\nAbort. Re-run with --force if you still want to continue.")
            return 2
    else:
        print("\nCurrent API/Modbus state already matches within tolerance.")

    if args.clear_test:
        target_schedule = {
            "mode": "self-consumption",
            "charge": [],
            "discharge": [],
        }
        mutation_description = "Clear schedule and verify fallback to self-consumption"
    else:
        candidate_schedule, mutation_description = derive_candidate_schedule(
            baseline_api,
            inverter_power_w=args.inverter_power_w,
            allow_create=args.allow_create,
        )
        target_schedule = {
            "mode": expected_mode_for_schedule(candidate_schedule),
            **strip_mode(candidate_schedule),
        }

    print("\nPlanned mutation:")
    print(f"- {mutation_description}")
    print(pretty_json(target_schedule))

    if not args.execute:
        print("\nRead-only mode. No Modbus write sent.")
        print("Run again with --execute to perform write, verify through API, and restore.")
        return 0

    restore_error: Optional[int] = None
    write_error: Optional[int] = None
    try:
        print("\nApplying candidate schedule through Modbus...")
        dump_modbus_entities(modbus_backend, "HA entities before Modbus write")
        try:
            apply_modbus_schedule(modbus_backend, target_schedule)
        except Exception as write_exc:
            print(f"Modbus write failed: {write_exc}")
            print(f"Backend status: {json.dumps(modbus_backend.context.status, indent=2, sort_keys=True)}")
            dump_modbus_entities(modbus_backend, "HA entities after failed Modbus write")
            print("Modbus schedule snapshot after failed write:")
            print(pretty_json(fetch_modbus_schedule(modbus_backend, modbus_context)))
            print("\nForcing HA entity refresh after failed write...")
            force_refresh_modbus_entities(modbus_backend)
            time.sleep(10)
            dump_modbus_entities(modbus_backend, "HA entities after forced refresh")
            print("Modbus schedule snapshot after forced refresh:")
            print(pretty_json(fetch_modbus_schedule(modbus_backend, modbus_context)))
            raise
        dump_modbus_entities(modbus_backend, "HA entities after Modbus write")

        print("Polling SAJ cloud API for read-back...")
        actual_after_write, diffs_after_write, attempt_after_write = wait_for_api_schedule(
            api_backend,
            expected_schedule=target_schedule,
            power_tolerance_w=args.power_tolerance_w,
            attempts=args.poll_attempts,
            interval_seconds=args.poll_interval_seconds,
        )
        if diffs_after_write:
            print("Cloud API did not converge to modified schedule:")
            for diff in diffs_after_write:
                print(f"- {diff}")
            print(pretty_json(actual_after_write))
            write_error = 3

        if write_error is None:
            print(f"Cloud API matched modified schedule after attempt {attempt_after_write}.")
            print(pretty_json(actual_after_write))

    finally:
        print("\nRestoring original schedule and mode...")
        try:
            restore_modbus_state(modbus_backend, baseline_api)
            dump_modbus_entities(modbus_backend, "HA entities after Modbus restore")
        except Exception as modbus_restore_error:
            print(f"Modbus restore failed: {modbus_restore_error}")
            dump_modbus_entities(modbus_backend, "HA entities after failed Modbus restore")
            restore_error = 4

        if restore_error is None:
            restore_attempts = max(args.poll_attempts, 18)
            restored_modbus, restore_modbus_diffs, restore_modbus_attempt = wait_for_modbus_schedule(
                modbus_backend,
                modbus_context,
                expected_schedule=baseline_api,
                power_tolerance_w=args.power_tolerance_w,
                attempts=restore_attempts,
                interval_seconds=args.poll_interval_seconds,
            )
            if restore_modbus_diffs:
                print("Modbus restore verification failed:")
                for diff in restore_modbus_diffs:
                    print(f"- {diff}")
                print(pretty_json(restored_modbus))
                restore_error = 4

        if restore_error is None:
            restored_api, restore_diffs, restore_attempt = wait_for_api_schedule(
                api_backend,
                expected_schedule=baseline_api,
                power_tolerance_w=args.power_tolerance_w,
                attempts=max(args.poll_attempts, 18),
                interval_seconds=args.poll_interval_seconds,
            )
            if restore_diffs:
                print("API restore verification failed:")
                for diff in restore_diffs:
                    print(f"- {diff}")
                print(pretty_json(restored_api))
                restore_error = 4

            if restore_error is None:
                print(f"Restore verified through Modbus after attempt {restore_modbus_attempt}.")
                print(pretty_json(restored_modbus))
                print(f"Restore verified through API after attempt {restore_attempt}.")
                print(pretty_json(restored_api))

    if restore_error is not None:
        return restore_error
    if write_error is not None:
        return write_error

    print("\nParity test passed: Modbus write was visible through SAJ cloud API and restore succeeded.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
