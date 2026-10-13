#!/usr/bin/env python3
"""Read the HEMS decision logs: what was decided, why, and what the whole plan looked like at that moment.

Files (written by the integration into /config/hems/ on the server):
  decision_trace.jsonl  one line per cycle: status, inputs, the comparison behind the action, plan segments
  plans.jsonl           one line per cycle: every planned quarter as compact arrays, with prices, load and PV
  events.jsonl          fetches, status and action changes, settings, PV gain

Usage:
  python3 scripts/hems_trace.py --pull                 # copy the logs from the server (SSH key from .env, see hems/AGENTS.md)
  python3 scripts/hems_trace.py tail [-n 20]           # one line per cycle
  python3 scripts/hems_trace.py show [TIME]            # one cycle in full: inputs, comparison, segments, every planned quarter
  python3 scripts/hems_trace.py why TIME [--cycle T]   # why the plan does what it does at TIME (default: latest plan)
  python3 scripts/hems_trace.py diff A B               # how the plan of cycle B differs from the plan of cycle A
  python3 scripts/hems_trace.py events [-n 30] [--type market]
  python3 scripts/hems_trace.py halog [-n 3000]        # the HEMS lines of the Home Assistant core log (REST proxy, read-only)
TIME is HH:MM (today, local), 'YYYY-MM-DD HH:MM' (local) or an ISO timestamp.
"""
import argparse
import importlib.util
import json
import re
import subprocess
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "hems" / "core"))
from hems.decision_log import when  # noqa: E402  (one day-aware time format for the log and for this reader)

DEFAULT_DIR = ROOT / "docs" / "hems" / "observations" / "data" / "trace"
REMOTE_DIR = "/config/hems"
FILES = ("decision_trace.jsonl", "plans.jsonl", "events.jsonl")
TZ = ZoneInfo("Europe/Amsterdam")
QUARTER = timedelta(minutes=15)
ACTION_NAME = {"c": "charge", "d": "discharge", "i": "idle"}
CODE_TEXT = {"s": "selling beats keeping", "b": "buying is cheaper than keeping", "h": "holding: neither selling nor buying beats keeping",
             "f": "holding at the reserve floor (selling would pay, the battery may not go lower)", "v": "holding because the battery is full",
             "-": "no comparison available"}


def load_jsonl(path: Path) -> list[dict]:
    """All records of a log, oldest first, including the rotated generations (<name>.3, .2, .1) when present."""
    rotated = [path.with_name(f"{path.name}.{n}") for n in (3, 2, 1)]
    records = []
    for file in [*rotated, path]:
        if file.exists():
            records += [json.loads(line) for line in file.read_text().splitlines() if line.strip()]
    return records


def parse_time(text: str, now: datetime | None = None) -> datetime:
    """UTC moment of 'HH:MM' (today, local), 'YYYY-MM-DD HH:MM' (local) or an ISO timestamp (naive means local)."""
    now = (now or datetime.now(TZ)).astimezone(TZ)
    text = text.strip()
    if len(text) <= 5 and ":" in text:
        hour, minute = map(int, text.split(":"))
        return now.replace(hour=hour, minute=minute, second=0, microsecond=0).astimezone(timezone.utc)
    moment = datetime.fromisoformat(text.replace(" ", "T"))
    return (moment if moment.tzinfo else moment.replace(tzinfo=TZ)).astimezone(timezone.utc)


def local(iso: str, fmt: str = "%H:%M") -> str:
    """An ISO timestamp as local time."""
    return datetime.fromisoformat(iso).astimezone(TZ).strftime(fmt)


def local_when(iso: str, reference_iso: str) -> str:
    """An ISO timestamp as local HH:MM, with '+1d ' when it lies on a later local day than the reference (plans run 48 h)."""
    return when(datetime.fromisoformat(iso), datetime.fromisoformat(reference_iso), TZ)


def cycle_at(records: list[dict], moment: datetime, key: str = "cycle") -> dict | None:
    """The latest record whose cycle (quarter start) is at or before `moment`."""
    best = None
    for record in records:
        stamp = record.get(key) or record.get("slot_start")
        if stamp and datetime.fromisoformat(stamp) <= moment:
            best = record
    return best


def format_tail(records: list[dict], count: int = 20) -> list[str]:
    """One line per cycle: local time, status, action, power, SoC, price source and the reason."""
    lines = []
    for r in records[-count:]:
        when = local(r["slot_start"], "%d %H:%M") if "slot_start" in r else local(r["now"], "%d %H:%M")
        flags = ("  <- changed" if r.get("action_changed") else "") + ("  <- plan shift" if "plan_shift" in r else "")
        if r.get("status") != "ok":
            lines.append(f"{when}  {r.get('status'):<16}{flags}")
            continue
        lines.append(f"{when}  {r.get('first_action', '?'):<9} {r.get('power_w', 0):>6} W  soc {r.get('soc_pct', 0):>5.1f}%  {r.get('price_source', ''):<6} {r.get('reason', '')}{flags}")
    return lines


def plan_rows(detail: dict) -> list[dict]:
    """The compact plan arrays as one dict per planned quarter."""
    start = datetime.fromisoformat(detail["start"])
    return [{"at": start + i * QUARTER, "action": ACTION_NAME[detail["a"][i]], "code": detail["c"][i], "w": detail["w"][i], "soc": detail["soc"][i],
             "grid": detail["grid"][i], "keep": detail["keep"][i], "sell": detail["sell"][i], "buy": detail["buy"][i], "imp": detail["imp"][i],
             "exp": detail["exp"][i], "load": detail["load"][i], "pv": detail["pv"][i]} for i in range(detail["n"])]


def plan_start(detail: dict) -> datetime:
    """The first quarter of a logged plan."""
    return datetime.fromisoformat(detail["start"])


def fmt(value: float | None, digits: int = 3) -> str:
    """A number with fixed decimals, or a dash for None."""
    return "-" if value is None else f"{value:.{digits}f}"


def format_plan_table(detail: dict, capacity_kwh: float = 25.0) -> list[str]:
    """Every planned quarter: action, watts, SoC, prices, load/PV, and the three values the decision compares."""
    lines = ["time       action     W     soc%   import export   load   pv    sell   keep   buy   why"]
    for r in plan_rows(detail):
        lines.append(f"{when(r['at'], plan_start(detail), TZ):<9}  {r['action']:<9}{r['w']:>6} {r['soc'] / capacity_kwh * 100:>6.1f}  {fmt(r['imp'])} {fmt(r['exp'])}  "
                     f"{fmt(r['load'])} {fmt(r['pv'])}  {fmt(r['sell'])} {fmt(r['keep'])} {fmt(r['buy'])}  {r['code']}")
    return lines


def format_show(record: dict, detail: dict | None) -> list[str]:
    """One cycle in full: the decision, the comparison, the inputs, the plan segments and (when logged) every quarter."""
    c = record.get("compare") or {}
    lines = [f"cycle {local(record['slot_start'], '%Y-%m-%d %H:%M')}  status {record['status']}  settings {record.get('settings')}",
             f"decision: {record.get('first_action')} {record.get('power_w')} W   soc {record.get('soc_pct')}%   {record.get('reason')}"]
    if c:
        lines.append(f"compare : sell {fmt(c.get('sell'))}  keep {fmt(c.get('keep'))}  buy {fmt(c.get('buy'))}  code {c.get('code')}  floor {c.get('at_floor')}  full {c.get('at_full')}")
        for name in ("best_sell_later", "best_buy_later"):
            if name in c:
                lines.append(f"          {name.replace('_', ' ')}: {c[name]['value']:.4f} at {local_when(c[name]['at'], record['slot_start'])}")
    lines.append("inputs  : " + ", ".join(f"{k}={v}" for k, v in (record.get("inputs") or {}).items()))
    lines.append(f"sources : prices {record.get('price_source')}, load {record.get('load_source')}, weather {record.get('weather')}, pv gain {record.get('pv_gain')}")
    if record.get("previous_action"):
        lines.append(f"previous: {record['previous_action']}" + ("  (changed)" if record.get("action_changed") else ""))
    if "plan_shift" in record:
        shift = record["plan_shift"]
        lines.append(f"shift   : planned {shift['was_w']} W for this quarter at {local_when(shift['planned_at'], record['slot_start'])}, now {shift['now_w']} W")
    lines.append("segments:")
    for s in record.get("segments", []):
        if "truncated" in s:
            lines.append(f"  ... {s['truncated']} more")
        else:
            lines.append(f"  {local_when(s['from'], record['slot_start'])} - {local_when(s['to'], record['slot_start'])}  {s['action']:<9} {s['avg_w']:>5} W  {s['kwh']:>5.1f} kWh  soc {s['soc_from_pct']:>5.1f}% -> {s['soc_to_pct']:>5.1f}%  price {fmt(s['avg_price'])}")
    if detail:
        lines += ["", "plan:", *format_plan_table(detail)]
    return lines


def explain_slot(detail: dict, moment: datetime) -> list[str]:
    """Why the plan does what it does in the quarter containing `moment`, from the numbers logged for that quarter."""
    rows = plan_rows(detail)
    index = int((moment - rows[0]["at"]) / QUARTER)
    if not 0 <= index < len(rows):
        return [f"{moment.astimezone(TZ):%a %H:%M} is outside this plan ({when(rows[0]['at'], rows[0]['at'], TZ)} to {when(rows[-1]['at'], rows[0]['at'], TZ)})"]
    r = rows[index]
    lines = [f"{r['at'].astimezone(TZ):%a %H:%M}: {r['action']} {r['w']} W, SoC after {r['soc']:.2f} kWh, grid {r['grid']:+.2f} kWh",
             f"  prices import {fmt(r['imp'], 4)} export {fmt(r['exp'], 4)}; house {fmt(r['load'])} kWh, PV {fmt(r['pv'])} kWh",
             f"  selling here is worth {fmt(r['sell'], 4)} per stored kWh, buying costs {fmt(r['buy'], 4)}, keeping is worth {fmt(r['keep'], 4)}",
             f"  => {CODE_TEXT[r['code']]}"]
    later = [x for x in rows[index + 1:] if x["sell"] is not None]
    if later and r["code"] in ("h", "f") and r["sell"] is not None:
        best = max(later, key=lambda x: x["sell"])
        if best["sell"] > r["sell"]:
            lines.append(f"  later is better: {when(best['at'], rows[0]['at'], TZ)} sells at {fmt(best['sell'], 4)} (+{best['sell'] - r['sell']:.4f})")
    return lines


def diff_plans(a: dict, b: dict) -> list[str]:
    """Quarters where cycle B plans something different from cycle A (action or power), matched by absolute time."""
    before = {r["at"]: r for r in plan_rows(a)}
    changes = []
    for r in plan_rows(b):
        old = before.get(r["at"])
        if old and (old["action"] != r["action"] or abs(old["w"] - r["w"]) > 0.1 * max(abs(old["w"]), abs(r["w"]), 1)):
            changes.append(f"{when(r['at'], plan_start(b), TZ):<9}  {old['action']} {old['w']} W -> {r['action']} {r['w']} W   (keep {fmt(old['keep'])} -> {fmt(r['keep'])}, import {fmt(old['imp'])} -> {fmt(r['imp'])})")
    overlap = sum(1 for r in plan_rows(b) if r["at"] in before)
    return [f"{len(changes)} of {overlap} overlapping quarters differ", *changes]


def format_events(events: list[dict], count: int = 30, kind: str | None = None) -> list[str]:
    """The newest events, optionally of one type, as 'time type details'."""
    chosen = [e for e in events if kind in (None, e["event"])][-count:]
    return [f"{local(e['ts'], '%d %H:%M:%S')}  {e['event']:<9} " + ", ".join(f"{k}={json.dumps(v, ensure_ascii=False)[:90]}" for k, v in e.items() if k not in ("ts", "event")) for e in chosen]


def pull(directory: Path) -> list[str]:
    """Copy the logs (and their rotated generations) from the server, using the SSH key and sudo of hems/deploy.py."""
    spec = importlib.util.spec_from_file_location("hems_deploy", ROOT / "hems" / "deploy.py")
    deploy = importlib.util.module_from_spec(spec)
    sys.modules["hems_deploy"] = deploy
    spec.loader.exec_module(deploy)
    env = deploy.parse_env((ROOT / ".env").read_text()) if (ROOT / ".env").exists() else {}
    target = deploy.target_from_env(env)
    directory.mkdir(parents=True, exist_ok=True)
    copied = []
    for name in FILES:
        for suffix in ("", ".1", ".2", ".3"):
            remote = f"{REMOTE_DIR}/{name}{suffix}"
            command = deploy.ssh_command(target, "none", f"sudo -n cat {remote}", batch=True)    # ControlPath=none: no shared connection
            done = subprocess.run(command, capture_output=True)
            if done.returncode == 0 and done.stdout:
                (directory / f"{name}{suffix}").write_bytes(done.stdout)
                copied.append(f"{name}{suffix} ({len(done.stdout) // 1024} KB)")
    return copied


TIMESTAMPED = re.compile(r"^(\x1b\[\d+m)?\d{4}-\d\d-\d\d \d\d:\d\d:\d\d")
ANSI = re.compile(r"\x1b\[[0-9;]*m")


def hems_log_lines(text: str) -> list[str]:
    """The HEMS entries of a Home Assistant core log, colour codes removed; the unprefixed lines of a multi-line entry (the plan tree) stay with it."""
    kept, inside = [], False
    for line in text.splitlines():
        if TIMESTAMPED.match(line):
            inside = "custom_components.hems" in line
        if inside:
            kept.append(ANSI.sub("", line))
    return kept


def fetch_core_log(entries: int) -> str:
    """The last `entries` lines of the Home Assistant core log through the REST proxy of the Supervisor (read-only; token from .env, never printed)."""
    spec = importlib.util.spec_from_file_location("hems_deploy", ROOT / "hems" / "deploy.py")
    deploy = importlib.util.module_from_spec(spec)
    sys.modules["hems_deploy"] = deploy
    spec.loader.exec_module(deploy)
    env = deploy.parse_env((ROOT / ".env").read_text())
    request = urllib.request.Request(env["HA_API_URL"].rstrip("/") + "/hassio/core/logs",       # HA_API_URL already ends in /api
                                     headers={"Authorization": "Bearer " + env["HA_API_TOKEN"], "Accept": "text/plain", "Range": f"entries=:-{entries}:{entries}"})
    return urllib.request.urlopen(request, timeout=90).read().decode(errors="replace")


def main() -> int:
    """Command line entry point."""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dir", type=Path, default=DEFAULT_DIR, help="where the logs are (default docs/hems/observations/data/trace)")
    parser.add_argument("--pull", action="store_true", help="first copy the logs from the server")
    sub = parser.add_subparsers(dest="command")
    tail = sub.add_parser("tail")
    tail.add_argument("-n", type=int, default=20)
    show = sub.add_parser("show")
    show.add_argument("time", nargs="?")
    why = sub.add_parser("why")
    why.add_argument("time")
    why.add_argument("--cycle")
    diff = sub.add_parser("diff")
    diff.add_argument("a")
    diff.add_argument("b")
    events = sub.add_parser("events")
    events.add_argument("-n", type=int, default=30)
    events.add_argument("--type")
    halog = sub.add_parser("halog")
    halog.add_argument("-n", type=int, default=3000, help="how many core-log lines to look through")
    args = parser.parse_args()
    if args.command == "halog":
        print("\n".join(hems_log_lines(fetch_core_log(args.n))) or "no HEMS lines in that stretch of the core log")
        return 0
    if args.pull:
        print("pulled:", ", ".join(pull(args.dir)) or "nothing (is the SSH key set up?)")
    if not args.command:
        return 0
    decisions, plans, evs = (load_jsonl(args.dir / name) for name in FILES)
    now = datetime.now(timezone.utc)
    if args.command == "tail":
        print("\n".join(format_tail(decisions, args.n)))
    elif args.command == "show":
        moment = parse_time(args.time) if args.time else now
        record = cycle_at(decisions, moment, "slot_start")
        detail = cycle_at(plans, moment)
        print("\n".join(format_show(record, detail if detail and detail["cycle"] == record["slot_start"] else None)) if record else "no such cycle")
    elif args.command == "why":
        plan = cycle_at(plans, parse_time(args.cycle) if args.cycle else now)
        print("\n".join(explain_slot(plan, parse_time(args.time))) if plan else "no plan logged")
    elif args.command == "diff":
        first, second = cycle_at(plans, parse_time(args.a)), cycle_at(plans, parse_time(args.b))
        print("\n".join(diff_plans(first, second)) if first and second else "plan not found")
    elif args.command == "events":
        print("\n".join(format_events(evs, args.n, args.type)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
