"""Task A: decision trace file, sensor attributes and log line."""

import json
import logging
import os
from datetime import datetime, timedelta, timezone

from app import decision_trace
from Tests.plan_replay import amsterdam_tz, make_config, replay  # noqa: F401

REQUIRED_KEYS = {
    "timestamp_utc", "timestamp_local", "soc", "temperature", "discharge_hours",
    "import_price", "export_price", "day_min_import", "ranges",
    "discharge_windows_before", "discharge_windows", "discharge_windows_after",
    "sell_buffer", "solar_aware", "precharge", "margin_gate", "final", "power_changes",
}


def test_each_generation_appends_one_readable_json_line(monkeypatch, amsterdam_tz, tmp_path):
    trace_path = tmp_path / "trace.jsonl"
    monkeypatch.setenv("DECISION_TRACE_PATH", str(trace_path))

    replay(monkeypatch, "12:00", 36, 15.0)
    replay(monkeypatch, "12:15", 38, 14.0)

    lines = trace_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    record = json.loads(lines[0])
    assert REQUIRED_KEYS <= set(record)
    assert record["timestamp_utc"].endswith("+00:00")
    assert record["timestamp_local"].endswith("+02:00")
    assert record["soc"] == 36
    assert record["discharge_hours"]["effective"] == 2
    assert record["solar_aware"]["applied"] is True
    assert record["solar_aware"]["deficit_kwh"] > 0
    assert record["solar_aware"]["grid_target_kwh"] is not None
    assert {"charge", "discharge"} <= set(record["final"])
    assert record["final"]["charge"][0]["power"] > 0
    assert {"required_soc", "main_charge_start"} <= set(record["sell_buffer"])
    window = record["discharge_windows"][0]
    assert {"decision", "reason", "rank", "needed_kwh", "available_kwh", "reserve_floor_soc"} <= set(window)


def test_dropped_and_truncated_windows_carry_their_reason(monkeypatch, amsterdam_tz, tmp_path):
    trace_path = tmp_path / "trace.jsonl"
    monkeypatch.setenv("DECISION_TRACE_PATH", str(trace_path))

    replay(monkeypatch, "17:00", 80, 0.0)  # 13.75 kWh above the floor < 16 kWh needed

    record = json.loads(trace_path.read_text().splitlines()[0])
    truncated = [w for w in record["discharge_windows"] if w["decision"] == "truncated"]
    assert truncated and truncated[0]["needed_kwh"] > truncated[0]["available_kwh"]
    assert "cut to" in truncated[0]["reason"]
    before = {w["start"]: w for w in record["discharge_windows_before"]}
    after = {w["start"]: w for w in record["discharge_windows_after"]}
    assert before.keys() == after.keys()
    assert any(before[k]["end"] != after[k]["end"] for k in before)


def test_sensor_exposes_last_record_and_one_liner_is_logged(monkeypatch, amsterdam_tz, caplog):
    updates = []
    with caplog.at_level(logging.INFO):
        replay(monkeypatch, "12:00", 36, 15.0, entity_updates=updates)

    entity, state, attributes = next(u for u in updates if u[0] == "decision")
    assert entity == "decision"
    assert state.startswith("🧭 Decision | SoC 36%") and len(state) <= 255
    assert REQUIRED_KEYS <= set(attributes)
    assert any(r.message == state for r in caplog.records if r.levelno == logging.INFO)
    assert len(json.dumps(attributes, default=str)) < 16 * 1024


def test_write_failure_never_breaks_planning(monkeypatch, amsterdam_tz, tmp_path):
    blocker = tmp_path / "file"
    blocker.write_text("x")
    monkeypatch.setenv("DECISION_TRACE_PATH", str(blocker / "sub" / "trace.jsonl"))

    schedule = replay(monkeypatch, "12:00", 36, 15.0)

    assert schedule["charge"]


def test_trace_can_be_disabled(monkeypatch, amsterdam_tz, tmp_path):
    trace_path = tmp_path / "trace.jsonl"
    monkeypatch.setenv("DECISION_TRACE_PATH", str(trace_path))
    config = make_config()
    config["decision_trace"]["enabled"] = False

    replay(monkeypatch, "12:00", 36, 15.0, config=config)

    assert not trace_path.exists()


def test_rotates_at_size_limit(tmp_path, monkeypatch):
    path = tmp_path / "trace.jsonl"
    now = datetime(2026, 10, 7, tzinfo=timezone.utc)
    record = {"timestamp_utc": now.isoformat(), "x": 1}
    monkeypatch.setattr(decision_trace, "MAX_TRACE_BYTES", 200)

    for _ in range(20):
        assert decision_trace.write_trace(str(path), record, now)

    assert os.path.exists(str(path) + ".1")
    assert path.stat().st_size < 200 + 60
    assert all(json.loads(line) for line in path.read_text().splitlines())


def test_rotates_after_14_days(tmp_path):
    path = tmp_path / "trace.jsonl"
    start = datetime(2026, 9, 20, tzinfo=timezone.utc)
    decision_trace.write_trace(str(path), {"timestamp_utc": start.isoformat()}, start)
    decision_trace.write_trace(str(path), {"timestamp_utc": start.isoformat(), "n": 2},
                               start + timedelta(days=13))
    assert not os.path.exists(str(path) + ".1")

    later = start + timedelta(days=14)
    decision_trace.write_trace(str(path), {"timestamp_utc": later.isoformat(), "n": 3}, later)

    assert os.path.exists(str(path) + ".1")
    assert len(path.read_text().splitlines()) == 1


def test_oversized_record_is_trimmed_for_the_sensor():
    record = {
        "timestamp_utc": "t", "timestamp_local": "t", "soc": 50, "final": {"charge": [], "discharge": []},
        "discharge_windows_before": [{"x": "y" * 50}] * 400,
    }
    attributes = decision_trace.fit_attributes(record)
    assert attributes["truncated"] and "discharge_windows_before" not in attributes
    assert len(json.dumps(attributes)) < decision_trace.MAX_ATTRIBUTE_BYTES
