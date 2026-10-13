"""Decision trace: one JSON line per decision, so 'why did we charge?' is answerable."""
import json
from datetime import datetime, timezone


def record(path: str, decision: dict) -> None:
    decision = {"ts": datetime.now(timezone.utc).isoformat(), **decision}
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(decision, ensure_ascii=False) + "\n")


def explain(plan, import_prices: list[float], export_prices: list[float]) -> dict:
    """Summarise a battery plan into a trace entry."""
    ch = [s for s in plan.slots if s.action == "charge"]
    dis = [s for s in plan.slots if s.action == "discharge"]
    def avg(sl, pr):
        e = sum(abs(s.battery_kwh) for s in sl)
        return sum(abs(s.battery_kwh) * pr[s.index] for s in sl) / e if e else None
    return {
        "charge_kwh": round(sum(s.battery_kwh for s in ch), 2),
        "discharge_kwh": round(-sum(s.battery_kwh for s in dis), 2),
        "avg_charge_import_price": avg(ch, import_prices),
        "avg_discharge_export_price": avg(dis, export_prices),
        "expected_saving_eur": round(plan.saving, 3),
        "first_action": plan.slots[0].action if plan.slots else None,
    }
