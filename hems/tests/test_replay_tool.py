import importlib.util
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "hems" / "core"))
spec = importlib.util.spec_from_file_location("hems_replay_tool", ROOT / "scripts" / "hems_replay.py")
tool = importlib.util.module_from_spec(spec)
sys.modules["hems_replay_tool"] = tool
spec.loader.exec_module(tool)

from hems.prices import PriceModel  # noqa: E402

FIRST_AFTER_FIXTURE = datetime(2026, 10, 15, 0, 0, tzinfo=timezone.utc)


def write_plans(path: Path, cycles: list[tuple[datetime, list[float], list[float]]]) -> None:
    """A plans.jsonl with the given (start, import, export) cycles."""
    path.write_text("\n".join(json.dumps({"start": start.isoformat(), "imp": imp, "exp": exp}) for start, imp, exp in cycles) + "\n")


def test_prices_after_the_recorder_export_come_from_the_logged_plans_and_a_later_cycle_wins(tmp_path, monkeypatch):
    """The replay of 15 Oct died with an IndexError because the export ends on 12 Oct; the logged plans carry every later day's prices."""
    plans = tmp_path / "plans.jsonl"
    write_plans(plans, [(FIRST_AFTER_FIXTURE, [0.30, 0.31, 0.32], [0.28, 0.29, 0.30]), (FIRST_AFTER_FIXTURE + timedelta(minutes=15), [0.35, 0.36], [0.33, 0.34])])
    monkeypatch.setattr(tool, "TRACE_PLANS", plans)
    later = tool.trace_prices()
    assert later[FIRST_AFTER_FIXTURE] == (0.30, 0.28) and later[FIRST_AFTER_FIXTURE + timedelta(minutes=15)] == (0.35, 0.33)
    prices = tool.load_prices(PriceModel(), later)
    assert prices.starts[-1] == FIRST_AFTER_FIXTURE + timedelta(minutes=30) and prices.import_eur_kwh[-1] == 0.36
    assert prices.starts == tuple(sorted(prices.starts)) and len(set(prices.starts)) == len(prices.starts)
    assert prices.import_eur_kwh[0] == tool.load_prices(PriceModel()).import_eur_kwh[0]


def test_a_period_without_prices_or_hourly_data_says_what_to_do_instead_of_an_index_error():
    """Both gaps stop with a message that names the fix."""
    prices = tool.load_prices(PriceModel())
    late = datetime(2026, 11, 1, tzinfo=timezone.utc)
    with pytest.raises(SystemExit, match="hems_trace.py --pull"):
        tool.build(prices, {}, late, late + timedelta(days=1), 25.0)
    first = prices.starts[10]
    with pytest.raises(SystemExit, match="hems_collect.py run"):
        tool.build(prices, {}, first, first + timedelta(hours=2), 25.0)
