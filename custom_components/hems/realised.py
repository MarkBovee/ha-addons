"""What actually happened, quarter by quarter: energy at the meter, its cost, and the same quarter for a battery in self-consumption only.

The ledger integrates live power readings (grid, PV, battery) into energy per quarter. When a quarter closes it is priced with the
import and export price HEMS had for it, and compared with a simulated baseline: the same PV and house load with the battery doing
plain self-consumption (charge from surplus, discharge to cover the house, never from or to the grid). It also keeps the forecast
HEMS made for that quarter, so forecast error and bias come from the same records.

Pure: no Home Assistant objects. The coordinator feeds it samples and prices and stores `state()` with a Home Assistant Store.
"""
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone, tzinfo
from math import sqrt
from typing import Any

QUARTER = timedelta(minutes=15)
MAX_GAP_S = 120.0            # a longer gap between samples is not integrated (HA restart, sensor outage): the quarter shows less coverage
KEEP_DAYS = 8                # quarter records kept for error statistics and the history view
KEEP_DAY_TOTALS = 400        # closed days kept for the week, month and year views (a few hundred bytes each)
DAY_SUMS = ("cost", "baseline_cost", "import_kwh", "export_kwh", "pv_kwh", "load_kwh", "ev_kwh", "import_price_sum")
MIN_COVERAGE = 0.6           # a quarter with less measured time is kept but left out of the money totals and error statistics
DEFAULT_BANDS = {"pv": (0.55, 1.35), "load": (0.7, 1.4)}      # P10/P90 ratio actual/forecast until there are enough own records
MIN_BAND_SAMPLES = 96


def quarter_start(moment: datetime) -> datetime:
    """The UTC start of the quarter that contains `moment`."""
    m = moment.astimezone(timezone.utc)
    return m.replace(minute=m.minute - m.minute % 15, second=0, microsecond=0)


@dataclass
class _Acc:
    """Energy of the open quarter so far (kWh; battery + charge) and the seconds it covers."""
    start: datetime
    import_kwh: float = 0.0
    export_kwh: float = 0.0
    pv_kwh: float = 0.0
    battery_kwh: float = 0.0
    ev_kwh: float = 0.0
    seconds: float = 0.0


@dataclass
class QuarterPrice:
    """What HEMS knew about a quarter when it began: its prices and the forecast it planned on."""
    import_eur_kwh: float
    export_eur_kwh: float
    pv_kwh: float | None = None
    load_kwh: float | None = None
    action: str | None = None
    other_action: str | None = None        # what the old battery manager said for this quarter (transition comparison), when configured


@dataclass
class PlannedQuarter:
    """One coming quarter of the plan, as the rest-of-day forecast needs it."""
    start: datetime
    import_eur_kwh: float
    export_eur_kwh: float
    pv_kwh: float
    load_kwh: float
    grid_kwh: float              # the plan's grid exchange: + import / - export
    soc_kwh: float               # the plan's SoC at the end of the quarter


@dataclass
class Ledger:
    """See the module docstring."""
    capacity_kwh: float
    floor_kwh: float
    max_kw: float
    round_trip_eff: float
    baseline_soc_kwh: float | None = None
    day: str | None = None                                  # local date of the 'today' totals
    today: dict[str, Any] = field(default_factory=lambda: _empty_day())
    total: dict[str, Any] = field(default_factory=lambda: {"cost": 0.0, "baseline_cost": 0.0, "stock_value": 0.0, "since": None})
    days: list[dict[str, Any]] = field(default_factory=list)       # closed days, see _day_row
    quarters: list[dict[str, Any]] = field(default_factory=list)
    _acc: _Acc | None = None
    _last: tuple[datetime, float, float, float] | None = None

    # ------------------------------------------------------------------ persistence

    def state(self) -> dict[str, Any]:
        """Everything worth keeping over a restart (the open quarter is not: it is incomplete anyway)."""
        return {"baseline_soc_kwh": self.baseline_soc_kwh, "day": self.day, "today": self.today, "total": self.total, "days": self.days[-KEEP_DAY_TOTALS:],
                "quarters": self.quarters}

    def restore(self, data: dict[str, Any] | None) -> None:
        """Take a stored state back; unknown or damaged data is ignored."""
        if not isinstance(data, dict):
            return
        self.baseline_soc_kwh = data.get("baseline_soc_kwh")
        self.day = data.get("day")
        self.today = {**self.today, **(data.get("today") or {})}
        self.total = {**self.total, **(data.get("total") or {})}
        self.days = [_upgrade_day(d) for d in data.get("days") or [] if isinstance(d, dict) and d.get("date")]
        self.quarters = list(data.get("quarters") or [])

    # ------------------------------------------------------------------ sampling

    def sample(self, now: datetime, grid_w: float | None, pv_w: float | None, battery_w: float | None,
               soc_kwh: float | None, prices: dict[datetime, QuarterPrice], tz: tzinfo, ev_w: float = 0.0) -> list[dict[str, Any]]:
        """Integrate the power since the last sample (held constant, left value) and close every quarter that ended; returns the closed records.

        A missing grid reading stops integration until it is back; missing PV or battery count as 0 W (no PV at night, idle battery)."""
        closed: list[dict[str, Any]] = []
        now = now.astimezone(timezone.utc)
        if self._acc is None:
            self._acc = _Acc(quarter_start(now))
        if self._last is not None:
            t0, g, p, b, e = self._last
            t = t0
            while t < now:
                boundary = self._acc.start + QUARTER
                step_end = min(now, boundary)
                dt = (step_end - t).total_seconds()
                if 0 < (now - t0).total_seconds() <= MAX_GAP_S and dt > 0:
                    h = dt / 3600
                    self._acc.import_kwh += max(g, 0) * h / 1000
                    self._acc.export_kwh += max(-g, 0) * h / 1000
                    self._acc.pv_kwh += max(p, 0) * h / 1000
                    self._acc.battery_kwh += b * h / 1000
                    self._acc.ev_kwh += max(e, 0) * h / 1000
                    self._acc.seconds += dt
                t = step_end
                if step_end == boundary:
                    rec = self._close(self._acc, prices.get(self._acc.start), soc_kwh, tz)
                    if rec:
                        closed.append(rec)
                    self._acc = _Acc(boundary)
        elif quarter_start(now) != self._acc.start:
            self._acc = _Acc(quarter_start(now))
        self._last = (now, grid_w, pv_w or 0.0, battery_w or 0.0, ev_w or 0.0) if grid_w is not None else None
        return closed

    # ------------------------------------------------------------------ closing a quarter

    def _baseline(self, pv_kwh: float, load_kwh: float, soc_start: float) -> tuple[float, float]:
        """Self-consumption only for one quarter: (grid kWh + import / - export, SoC at the end)."""
        one_way = sqrt(max(0.01, self.round_trip_eff))
        limit = self.max_kw / 4
        net = pv_kwh - load_kwh
        soc = soc_start
        if net > 0:
            charge = min(net, limit, max(0.0, (self.capacity_kwh - soc) / one_way))
            soc += charge * one_way
            return -(net - charge), soc
        discharge = min(-net, limit, max(0.0, (soc - self.floor_kwh) * one_way))
        soc -= discharge / one_way
        return (-net) - discharge, soc

    def _close(self, acc: _Acc, price: QuarterPrice | None, soc_kwh: float | None, tz: tzinfo) -> dict[str, Any] | None:
        """Price the quarter, run the baseline, update the totals; None for a quarter without any measured time."""
        if acc.seconds <= 0:
            return None
        coverage = min(1.0, acc.seconds / QUARTER.total_seconds())
        grid = acc.import_kwh - acc.export_kwh
        house = max(0.0, grid + acc.pv_kwh - acc.battery_kwh)          # everything behind the meter, the car included
        load = max(0.0, house - acc.ev_kwh)                             # the base load, as HEMS forecasts it (the car is planned apart)
        if self.baseline_soc_kwh is None:
            self.baseline_soc_kwh = soc_kwh if soc_kwh is not None else self.capacity_kwh / 2
        base_grid, base_soc = self._baseline(acc.pv_kwh, house, self.baseline_soc_kwh)
        self.baseline_soc_kwh = base_soc
        rec: dict[str, Any] = {"t": acc.start.isoformat(), "coverage": round(coverage, 2), "import_kwh": round(acc.import_kwh, 4),
                               "export_kwh": round(acc.export_kwh, 4), "pv_kwh": round(acc.pv_kwh, 4), "load_kwh": round(load, 4), "ev_kwh": round(acc.ev_kwh, 4),
                               "battery_kwh": round(acc.battery_kwh, 4), "baseline_grid_kwh": round(base_grid, 4), "baseline_soc_kwh": round(base_soc, 3)}
        local_day = acc.start.astimezone(tz).date().isoformat()
        self._roll_day(local_day)
        if price is not None:
            cost = acc.import_kwh * price.import_eur_kwh - acc.export_kwh * price.export_eur_kwh
            base_cost = max(base_grid, 0) * price.import_eur_kwh - max(-base_grid, 0) * price.export_eur_kwh
            rec.update({"import_price": price.import_eur_kwh, "export_price": price.export_eur_kwh, "cost": round(cost, 5),
                        "baseline_cost": round(base_cost, 5), "fc_pv_kwh": price.pv_kwh, "fc_load_kwh": price.load_kwh, "planned": price.action,
                        "other": price.other_action})
            if coverage >= MIN_COVERAGE:
                self._add_to_today(rec, cost, base_cost, price.import_eur_kwh)
        if soc_kwh is not None:
            gap = soc_kwh - base_soc                                    # energy the real battery holds above the baseline's
            if self.today.get("stock_gap_start") is None:
                self.today["stock_gap_start"] = gap
            self.today["stock_gap_end"] = gap
        self.quarters.append(rec)
        cutoff = (acc.start - timedelta(days=KEEP_DAYS)).isoformat()
        self.quarters = [q for q in self.quarters if q["t"] >= cutoff]
        return rec

    def _add_to_today(self, rec: dict[str, Any], cost: float, base_cost: float, import_price: float) -> None:
        """Count one fully enough measured quarter in today's and the running totals."""
        for key in ("import_kwh", "export_kwh", "pv_kwh", "load_kwh", "ev_kwh"):
            self.today[key] = self.today.get(key, 0.0) + rec[key]
        self.today["cost"] += cost
        self.today["baseline_cost"] += base_cost
        self.today["import_price_sum"] = self.today.get("import_price_sum", 0.0) + import_price
        self.today["priced_quarters"] = self.today.get("priced_quarters", 0) + 1     # its own count: a day restored from before this field has fewer
        self.today["quarters"] += 1
        self.total["cost"] += cost
        self.total["baseline_cost"] += base_cost
        self.total["since"] = self.total["since"] or rec["t"]

    def _roll_day(self, local_day: str) -> None:
        """Start new 'today' totals on a new local day and keep the closed day."""
        if self.day == local_day:
            return
        if self.day is not None and self.today.get("quarters"):
            row = _day_row(self.day, self.today)
            self.days.append(row)
            self.total["stock_value"] = self.total.get("stock_value", 0.0) + row["stock_value"]
        carried = self.today.get("stock_gap_end")                       # a day starts with the stock difference the last one ended with
        self.day = local_day
        self.today = _empty_day()
        self.today["stock_gap_start"] = carried

    # ------------------------------------------------------------------ what the sensors show

    def result_today(self) -> dict[str, float]:
        """Net cost today at the meter, the baseline's, and the gain (baseline minus actual; positive = better than self-consumption)."""
        return {"cost": round(self.today["cost"], 2), "baseline_cost": round(self.today["baseline_cost"], 2),
                "gain": round(self.today["baseline_cost"] - self.today["cost"], 2), "quarters": self.today["quarters"]}

    def gain_total(self) -> float:
        """Gain over self-consumption since the ledger started, with the stored-energy difference valued (see _day_row)."""
        today_stock = _day_row(self.day, self.today)["stock_value"] if self.day else 0.0
        return round(self.total["baseline_cost"] - self.total["cost"] + self.total.get("stock_value", 0.0) + today_stock, 2)

    def forecast_error(self, key: str, days: int = 7) -> dict[str, Any] | None:
        """Mean absolute error and bias (forecast minus actual) of the PV or load forecast in kWh per day, over the last `days` days."""
        fc, act = f"fc_{key}_kwh", f"{key}_kwh"
        rows = [q for q in self.quarters if q.get(fc) is not None and q.get("coverage", 0) >= MIN_COVERAGE][-days * 96:]
        if len(rows) < 8:
            return None
        n_days = max(1.0, len(rows) / 96)
        abs_err = sum(abs(q[fc] - q[act]) for q in rows)
        bias = sum(q[fc] - q[act] for q in rows)
        actual = sum(q[act] for q in rows)
        return {"mae_kwh_day": round(abs_err / n_days, 2), "bias_kwh_day": round(bias / n_days, 2),
                "relative": round(abs_err / actual, 3) if actual > 0 else None, "quarters": len(rows)}

    def bands(self, key: str) -> dict[str, Any]:
        """P10/P90 of actual/forecast for the PV or load forecast, from the own records once there are enough; otherwise a stated default."""
        fc, act = f"fc_{key}_kwh", f"{key}_kwh"
        ratios = sorted(q[act] / q[fc] for q in self.quarters if (q.get(fc) or 0) > 0.02 and q.get("coverage", 0) >= MIN_COVERAGE)
        if len(ratios) < MIN_BAND_SAMPLES:
            lo, hi = DEFAULT_BANDS[key]
            return {"p10": lo, "p90": hi, "source": "default", "samples": len(ratios)}
        pick = lambda f: ratios[min(len(ratios) - 1, int(f * (len(ratios) - 1)))]
        return {"p10": round(pick(0.1), 3), "p90": round(pick(0.9), 3), "source": "measured", "samples": len(ratios)}

    def rest_of_day(self, planned: list[PlannedQuarter], tz: tzinfo) -> dict[str, float] | None:
        """What today should still bring if the plan runs: the plan's grid cost of the remaining quarters of today against the same
        self-consumption baseline the ledger measures with, and the change in stored-energy difference, valued as in _day_row.

        `end_of_day` adds this to today's measured gain. None without a plan for today or before the first measured quarter."""
        if not self.day or self.baseline_soc_kwh is None:
            return None
        rest = [q for q in planned if local_date(q.start, tz).isoformat() == self.day]
        if not rest:
            return None
        cost = base_cost = 0.0
        base_soc = self.baseline_soc_kwh
        for q in rest:
            base_grid, base_soc = self._baseline(q.pv_kwh, q.load_kwh, base_soc)
            cost += _price(q.grid_kwh, q)
            base_cost += _price(base_grid, q)
        today = _day_row(self.day, self.today)
        avg_import = today["avg_import"] or sum(q.import_eur_kwh for q in rest) / len(rest)
        gap_now = self.today.get("stock_gap_end")
        stock_value = (rest[-1].soc_kwh - base_soc - gap_now) * avg_import if gap_now is not None else 0.0
        gain = base_cost - cost + stock_value
        return {"cost": round(cost, 2), "baseline_cost": round(base_cost, 2), "stock_value": round(stock_value, 2), "gain": round(gain, 2),
                "end_of_day": round(today["gain"] + gain, 2), "quarters": len(rest)}

    def daily(self) -> list[dict[str, Any]]:
        """Closed days (up to KEEP_DAY_TOTALS) plus today, each as _day_row; the panel sums them into weeks, months and years."""
        rows = list(self.days)
        if self.day:
            rows.append({**_day_row(self.day, self.today), "today": True})
        return rows


def _price(grid_kwh: float, q: PlannedQuarter) -> float:
    """Cost of a grid exchange: import at the import price, export at the export price."""
    return grid_kwh * q.import_eur_kwh if grid_kwh > 0 else grid_kwh * q.export_eur_kwh


def _upgrade_day(row: dict[str, Any]) -> dict[str, Any]:
    """A stored day from before the energy fields: fill them with zero and add the gain, so every row has one shape."""
    filled = {"quarters": 0, "avg_import": 0.0, "stock_kwh": 0.0, "stock_value": 0.0,
              **{k: 0.0 for k in DAY_SUMS if k != "import_price_sum"}, **row}
    return {**filled, "gain": round(filled["baseline_cost"] - filled["cost"] + filled["stock_value"], 4)}


def _empty_day() -> dict[str, Any]:
    """Fresh totals for one local day."""
    return {**{k: 0.0 for k in DAY_SUMS}, "quarters": 0, "priced_quarters": 0, "stock_gap_start": None, "stock_gap_end": None}


def _day_row(day: str, totals: dict[str, Any]) -> dict[str, Any]:
    """One day as kept and shown: money, energy, and the gain over self-consumption.

    The real battery and the baseline end a day with different amounts stored; without a value for that, a day that charges for an
    evening sale (or ends full for tomorrow) looks like a loss. The change in that difference is valued at the day's average import
    price, the price the stored energy replaces. Days kept before this field existed carry no stock value."""
    quarters = totals.get("quarters") or 0
    priced = totals.get("priced_quarters") or 0
    avg_import = totals.get("import_price_sum", 0.0) / priced if priced else 0.0
    start, end = totals.get("stock_gap_start"), totals.get("stock_gap_end")
    stock_kwh = end - start if start is not None and end is not None else 0.0
    row = {"date": day, "quarters": quarters, **{k: round(totals.get(k, 0.0), 4) for k in DAY_SUMS if k != "import_price_sum"},
           "avg_import": round(avg_import, 4), "stock_kwh": round(stock_kwh, 3), "stock_value": round(stock_kwh * avg_import, 4)}
    row["gain"] = round(row["baseline_cost"] - row["cost"] + row["stock_value"], 4)
    return row


def local_date(moment: datetime, tz: tzinfo) -> date:
    """The local calendar date of a moment."""
    return moment.astimezone(tz).date()
