import json
from datetime import datetime, timedelta, timezone

from test_rolling import recorded_day

from hems.battery import BatteryConfig
from hems.decision_log import best_later, cycle_line, event_line, plan_detail, plan_segments, plan_tree, settings_snapshot, when
from hems.forecast import LOCAL_TZ
from hems.prices import PriceModel
from hems.rolling import HorizonInputs, plan_next
from hems.trace import TraceWriter


def decision_at(hour: int, soc_kwh: float = 12.0):
    """A decision on the wide-spread day of 6 Oct, planned from `hour` local with some energy in the battery."""
    now = datetime(2026, 10, 6, hour, 7, tzinfo=LOCAL_TZ)
    return plan_next(HorizonInputs(now, soc_kwh, recorded_day("2026-10-06"), {}, {}), BatteryConfig())


def test_segments_cover_the_plan_without_gaps_and_chain_the_soc():
    """Runs of one action tile the whole horizon, and each run starts at the SoC where the previous one ended."""
    d = decision_at(12)
    segments = plan_segments(d.plan, d.slots, d.slot_start, 12.0, 25.0)
    assert segments[0]["from"] == d.slot_start.isoformat()
    assert all(a["to"] == b["from"] for a, b in zip(segments, segments[1:]))
    assert segments[-1]["to"] == (d.slot_start + len(d.plan.slots) * timedelta(minutes=15)).isoformat()
    assert all(a["soc_to_pct"] == b["soc_from_pct"] for a, b in zip(segments, segments[1:]))
    assert any(s["action"] == "discharge" and s["avg_price"] > 0.4 and s["avg_w"] > 5000 for s in segments)


def test_a_long_plan_is_cut_at_the_segment_limit_and_says_so():
    """The limit keeps the decision record small; the last entry reports how many runs were left out."""
    d = decision_at(0)
    segments = plan_segments(d.plan, d.slots, d.slot_start, 12.0, 25.0, limit=2)
    assert len(segments) == 3 and segments[-1]["truncated"] >= 1


def test_best_later_names_what_keep_is_waiting_for():
    """The best later sell is the maximum sell value after now, with its time."""
    d = decision_at(10)
    later = best_later(d.plan, d.slot_start)
    top = max((s.sell_value, i) for i, s in enumerate(d.plan.slots) if i and s.sell_value is not None)
    assert later["best_sell_later"] == {"at": (d.slot_start + top[1] * timedelta(minutes=15)).isoformat(), "value": round(top[0], 4)}
    assert later["best_buy_later"]["value"] > 0


def test_the_decision_trace_carries_the_comparison_and_the_shape_of_the_plan():
    """compare has the numbers behind the reason; segments describe the whole plan."""
    d = decision_at(19, soc_kwh=20.0)
    compare = d.trace["compare"]
    assert compare["code"] == "sell" and compare["sell"] > compare["keep"]
    assert d.trace["segments"] and d.trace["reason"].startswith("sell")


def test_plan_detail_is_compact_parallel_arrays_that_match_the_plan():
    """Every array has one entry per planned quarter and agrees with the plan it describes."""
    d = decision_at(12)
    detail = plan_detail(d)
    n = len(d.plan.slots)
    assert detail["n"] == n and len(detail["a"]) == n and len(detail["c"]) == n
    for key in ("w", "soc", "grid", "keep", "sell", "buy", "imp", "exp", "load", "pv"):
        assert len(detail[key]) == n, key
    assert detail["a"] == "".join({"charge": "c", "discharge": "d", "idle": "i"}[p.action] for p in d.plan.slots)
    assert detail["imp"][0] == round(d.slots[0].import_price, 4) and detail["w"][0] == round(d.command.power_w)
    assert len(json.dumps(detail, separators=(",", ":"))) < 70 * n          # about 60 bytes per quarter


def test_settings_snapshot_changes_its_hash_only_when_a_setting_changes():
    """The hash makes a settings change between two cycles visible."""
    base = settings_snapshot({"battery": BatteryConfig(), "prices": PriceModel()})
    assert base["hash"] == settings_snapshot({"battery": BatteryConfig(), "prices": PriceModel()})["hash"]
    assert base["hash"] != settings_snapshot({"battery": BatteryConfig(min_profit_margin=0.05), "prices": PriceModel()})["hash"]
    assert base["values"]["battery"]["min_profit_margin"] == 0.10


def test_trace_writer_keeps_several_generations_and_can_write_compact_lines(tmp_path):
    """With generations=2 both .1 and .2 survive a second rotation; compact lines have no spaces after separators."""
    fixed = datetime(2026, 10, 13, 12, 0, tzinfo=timezone.utc)
    path = tmp_path / "plans.jsonl"
    writer = TraceWriter(path, clock=lambda: fixed, max_bytes=60, compact=True, generations=2)
    for n in range(6):
        writer.write({"n": n, "pad": "x" * 40})
    assert path.with_name("plans.jsonl.1").exists() and path.with_name("plans.jsonl.2").exists()
    assert not path.with_name("plans.jsonl.3").exists()
    assert '"n":5' in path.read_text() or '"n":4' in path.read_text()


# ---- text for the Home Assistant log ------------------------------------------------------------------------

def record_at(hour: int, soc_kwh: float = 12.0) -> dict:
    """The decision record the integration writes for a cycle (trace of the decision)."""
    d = decision_at(hour, soc_kwh)
    return {"status": "ok", "price_source": "market", **d.trace}


def test_a_time_on_another_day_than_the_plan_start_says_so():
    """A plan of 48 hours crosses midnight: 07:30 tomorrow must not read as 07:30 today."""
    start = datetime(2026, 10, 13, 12, 0, tzinfo=timezone.utc)
    assert when(start + timedelta(hours=1), start, LOCAL_TZ) == "15:00"
    assert when(start + timedelta(hours=18), start, LOCAL_TZ) == "+1d 08:00"       # 12:00 UTC is 14:00 local, so +18 h is 08:00 tomorrow
    assert when(start + timedelta(hours=44), start, LOCAL_TZ) == "+2d 10:00"
    assert when(start - timedelta(hours=15), start, LOCAL_TZ) == "-1d 23:00"
    assert when(start - timedelta(hours=14), start, LOCAL_TZ) == "00:00"          # local midnight is still the same local day


def test_the_cycle_line_carries_the_decision_the_comparison_and_the_day_of_the_best_later_sale():
    """One line says what, why (sell/keep/buy), and when keep is waiting for, with the day for tomorrow."""
    line = cycle_line(record_at(12), LOCAL_TZ)
    assert line.startswith("HEMS 12:00 ok: ") and "sell " in line and "keep " in line and "buy " in line and "best sell later" in line
    assert "quarters, prices market" in line and "expected saving" in line
    assert "\n" not in line


def test_a_failed_cycle_is_one_line_with_the_status():
    """Without a decision the line is the status, so the log shows why nothing was planned."""
    assert cycle_line({"status": "no_soc"}, LOCAL_TZ) == "HEMS no_soc: no decision this quarter"


def test_the_plan_tree_lists_every_charge_and_discharge_window_with_their_day():
    """The tree names the windows of the whole plan, idle stretches are the gaps between them."""
    record = record_at(0)
    tree = plan_tree(record, LOCAL_TZ)
    windows = [s for s in record["segments"] if s.get("action") in ("charge", "discharge")]
    assert tree[0].startswith("HEMS plan from 00:00") and len(tree) == 1 + len(windows)
    assert any(" charge " in line for line in tree) and any(" discharge " in line for line in tree)
    assert plan_tree({"status": "no_soc"}, LOCAL_TZ) == []


def test_an_idle_plan_says_so_instead_of_an_empty_tree():
    """No windows still gives a readable line."""
    flat = {"slot_start": "2026-10-13T12:00:00+00:00", "horizon_slots": 8, "expected_saving_eur": 0.0,
            "segments": [{"from": "2026-10-13T12:00:00+00:00", "to": "2026-10-13T14:00:00+00:00", "action": "idle", "kwh": 0, "avg_w": 0,
                          "soc_from_pct": 40, "soc_to_pct": 40, "avg_price": None}]}
    assert plan_tree(flat, LOCAL_TZ)[-1] == "  no charge or discharge planned"


def test_an_event_line_stays_one_readable_line_however_large_the_event_is():
    """Big values (the settings of a cycle) are cut, small ones are kept whole."""
    line = event_line("settings", {"hash": "ab12cd34", "values": {"battery": {"x": "y" * 500}}, "previous": None})
    assert line.startswith("HEMS event settings hash=\"ab12cd34\"") and "previous=null" in line and line.count("\n") == 0 and len(line) < 720
    assert event_line("retry", {"in_seconds": 60.0, "status": "no_soc"}) == 'HEMS event retry in_seconds=60.0 status="no_soc"'
