import importlib.util
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "hems" / "core"))
spec = importlib.util.spec_from_file_location("hems_trace_tool", ROOT / "scripts" / "hems_trace.py")
tool = importlib.util.module_from_spec(spec)
sys.modules["hems_trace_tool"] = tool
spec.loader.exec_module(tool)

from hems.battery import BatteryConfig  # noqa: E402
from hems.decision_log import plan_detail  # noqa: E402
from hems.prices import PriceSeries  # noqa: E402
from hems.rolling import HorizonInputs, plan_next  # noqa: E402

START = datetime(2026, 10, 6, 12, 0, tzinfo=timezone.utc)


def decision(soc_kwh: float = 5.0, spread: float = 0.30, offset: int = 0, quarters: int = 40):
    """A plan over 40 quarters: cheap first, a price peak later, so it charges, holds and sells."""
    starts = tuple(START + timedelta(minutes=15 * i) for i in range(quarters))
    imp = tuple(0.20 if i < 12 else (0.20 + spread if 24 <= i < 32 else 0.28) for i in range(quarters))
    exp = tuple(p - 0.02 for p in imp)
    now = START + timedelta(minutes=15 * offset)
    return plan_next(HorizonInputs(now, soc_kwh, PriceSeries(starts, imp, exp), {}, {}), BatteryConfig())


def records(d):
    """The decision record as the integration writes it, plus the full plan."""
    trace = {"ts": "2026-10-06T12:00:20+00:00", "status": "ok", "dry_run": True, "settings": "ab12cd34", **d.trace, "previous_action": None, "action_changed": False}
    return trace, plan_detail(d)


def test_times_are_read_as_local_unless_they_carry_a_zone():
    """HH:MM means today local, a bare date-time is local, an offset is honoured."""
    now = datetime(2026, 10, 6, 9, 0, tzinfo=timezone.utc)
    assert tool.parse_time("16:30", now) == datetime(2026, 10, 6, 14, 30, tzinfo=timezone.utc)
    assert tool.parse_time("2026-10-06 19:00") == datetime(2026, 10, 6, 17, 0, tzinfo=timezone.utc)
    assert tool.parse_time("2026-10-06T19:00:00+00:00") == datetime(2026, 10, 6, 19, 0, tzinfo=timezone.utc)


def test_rotated_logs_are_read_oldest_first_and_a_cycle_is_found_by_time(tmp_path):
    """<name>.2, .1, then the live file; the cycle at a moment is the latest one at or before it."""
    path = tmp_path / "plans.jsonl"
    for suffix, cycle in ((".2", "2026-10-06T10:00:00+00:00"), (".1", "2026-10-06T11:00:00+00:00"), ("", "2026-10-06T12:00:00+00:00")):
        (tmp_path / f"plans.jsonl{suffix}").write_text(json.dumps({"cycle": cycle}) + "\n")
    loaded = tool.load_jsonl(path)
    assert [r["cycle"][11:13] for r in loaded] == ["10", "11", "12"]
    assert tool.cycle_at(loaded, datetime(2026, 10, 6, 11, 30, tzinfo=timezone.utc))["cycle"].startswith("2026-10-06T11")
    assert tool.cycle_at(loaded, datetime(2026, 10, 6, 9, 0, tzinfo=timezone.utc)) is None


def test_tail_shows_action_reason_and_marks_changes_and_failures():
    """One line per cycle; a non-ok status is shown as such, a changed action is flagged."""
    trace, _ = records(decision())
    trace["action_changed"] = True
    failed = {"status": "no_soc", "now": "2026-10-06T12:15:00+00:00"}
    lines = tool.format_tail([trace, failed])
    assert trace["reason"] in lines[0] and "<- changed" in lines[0] and lines[1].split()[2] == "no_soc"


def test_show_lists_the_comparison_the_segments_and_every_planned_quarter():
    """The full view has the decision, sell/keep/buy, the segments and one table row per quarter."""
    trace, detail = records(decision())
    text = "\n".join(tool.format_show(trace, detail))
    assert "compare : sell" in text and "segments:" in text and "best sell later" in text
    assert len([line for line in tool.format_plan_table(detail)]) == detail["n"] + 1


def test_why_explains_a_quarter_and_points_at_a_better_later_one():
    """For a held quarter the explanation names the comparison and, when it exists, the later quarter that pays more."""
    _, detail = records(decision(soc_kwh=15.0))
    rows = tool.plan_rows(detail)
    held = next(r for r in rows[:24] if r["code"] == "h" and r["sell"] is not None)
    text = "\n".join(tool.explain_slot(detail, held["at"]))
    assert "keeping is worth" in text and "holding" in text
    assert "outside this plan" in tool.explain_slot(detail, START + timedelta(days=2))[0]


def test_diff_names_the_quarters_where_the_new_plan_differs():
    """Replanning from a fuller battery changes some quarters; identical plans differ nowhere."""
    _, first = records(decision(soc_kwh=5.0))
    _, same = records(decision(soc_kwh=5.0))
    _, other = records(decision(soc_kwh=22.0))
    assert tool.diff_plans(first, same)[0].startswith("0 of")
    changed = tool.diff_plans(first, other)
    assert not changed[0].startswith("0 of") and "->" in changed[1]


def test_events_can_be_filtered_by_type():
    """Only events of the requested type, newest last."""
    events = [{"ts": "2026-10-06T12:00:00+00:00", "event": "market", "known_quarters": 96},
              {"ts": "2026-10-06T12:01:00+00:00", "event": "status", "from": None, "to": "ok"}]
    assert len(tool.format_events(events)) == 2
    only = tool.format_events(events, kind="market")
    assert len(only) == 1 and "known_quarters=96" in only[0]


def test_times_after_midnight_carry_their_day_in_every_view():
    """A plan that runs past local midnight shows '+1d' on the segments, the plan table, and 'later is better', so 07:30 is never ambiguous."""
    d = decision(offset=0, quarters=120)                     # 12:00 UTC = 14:00 local, 30 hours
    trace, detail = records(d)
    shown = "\n".join(tool.format_show(trace, detail))
    assert "+1d " in shown and shown.count("+1d ") >= 3
    assert any(line.startswith("+1d ") for line in tool.format_plan_table(detail))
    first_day = [line for line in tool.format_plan_table(detail)[1:] if not line.startswith("+1d")]
    assert first_day and all(not line.startswith("+") for line in first_day)


def test_the_core_log_reader_keeps_hems_entries_with_their_plan_tree_and_drops_the_rest():
    """Colour codes go, an unprefixed continuation line stays with its HEMS entry, other integrations' lines (and their tracebacks) are left out."""
    log = "\n".join([
        "\x1b[32m2026-10-13 14:11:56.036 INFO (MainThread) [custom_components.hems.coordinator] HEMS 14:00 ok: idle 0 W\x1b[0m",
        "\x1b[32m2026-10-13 14:11:56.036 INFO (MainThread) [custom_components.hems.coordinator] HEMS plan from 14:00, 136 quarters:",
        "  charge    +1d 00:00 - +1d 01:00   7730 W    7.7 kWh  soc 30% -> 61%  @0.263\x1b[0m",
        "\x1b[33m2026-10-13 14:12:00.000 WARNING (MainThread) [homeassistant.components.other] something else\x1b[0m",
        "  File \"/usr/src/other.py\", line 1, in run",
        "\x1b[32m2026-10-13 14:15:20.277 INFO (MainThread) [custom_components.hems.coordinator] HEMS 14:15 ok: idle 0 W\x1b[0m"])
    lines = tool.hems_log_lines(log)
    assert [line[:23] for line in lines if line[:2] == "20"] == ["2026-10-13 14:11:56.036"] * 2 + ["2026-10-13 14:15:20.277"]
    assert "  charge    +1d 00:00 - +1d 01:00   7730 W    7.7 kWh  soc 30% -> 61%  @0.263" in lines
    assert all("\x1b" not in line and "other" not in line for line in lines) and len(lines) == 4
