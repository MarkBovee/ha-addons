"""Replay: run the rolling planner over recorded days and account for it exactly like what really happened.

The simulated battery is the contract fake (limits, losses, device minimum), the planner only sees what it
would have known at each quarter (prices published after `publish_hour`, no future load or PV unless the
caller passes the oracle). Both the simulation and the recorded battery flows go through `account`, so the
comparison does not depend on sensor quirks that cancel out.
"""
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Callable, Mapping
from zoneinfo import ZoneInfo

from hems.battery import BatteryConfig
from hems.contracts import BatteryLimits
from hems.fakes import FakeBattery
from hems.forecast import LOCAL_TZ
from hems.prices import PriceSeries
from hems.rolling import QUARTER, Decision, HorizonInputs, plan_next, plan_shift
from hems.slots import SLOT_H
from hems.terminal import reference_peak


@dataclass(frozen=True)
class ReplayData:
    """Recorded quarters on a contiguous UTC grid. Energies in kWh per quarter."""
    prices: PriceSeries
    house_kwh: tuple[float, ...]             # base load (house minus EV)
    pv_kwh: tuple[float, ...]
    soc0_kwh: float
    recorded_battery_kwh: tuple[float, ...] | None = None    # what the real battery did, AC side, + charge


@dataclass(frozen=True)
class Account:
    """Cost of one battery behaviour over the replayed quarters."""
    cost_eur: float                          # cash grid cost
    baseline_eur: float                      # grid cost with no battery
    soc_delta_kwh: float                     # end minus start SoC

    def valued_saving(self, soc_value_eur_kwh: float) -> float:
        """Saving versus no battery, with the SoC left behind valued at what refilling it would cost."""
        return self.baseline_eur - self.cost_eur + self.soc_delta_kwh * soc_value_eur_kwh


@dataclass
class ReplayResult:
    decisions: list[Decision] = field(default_factory=list)
    battery_kwh: list[float] = field(default_factory=list)    # simulated AC flow per quarter, + charge
    soc_kwh: list[float] = field(default_factory=list)        # at the end of each quarter
    shifts: list[dict] = field(default_factory=list)


def known_until(now: datetime, tz: ZoneInfo, publish_hour: int) -> datetime:
    """End of the prices known at `now`: today's local midnight, plus tomorrow once published."""
    local = now.astimezone(tz)
    midnight = (local + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return midnight + timedelta(days=1) if local.hour >= publish_hour else midnight


def slot_cost(import_price: float, export_price: float, house: float, pv: float, battery_kwh: float) -> float:
    """Cash cost of one quarter: grid exchange at the import/export price."""
    grid = house - pv + battery_kwh
    return grid * (import_price if grid > 0 else export_price)


def account(data: ReplayData, battery_kwh: list[float] | tuple[float, ...], soc_delta_kwh: float) -> Account:
    """Account a battery behaviour (one AC flow per quarter) against the recorded house and PV."""
    p = data.prices
    cost = sum(slot_cost(i, e, h, v, b) for i, e, h, v, b in
               zip(p.import_eur_kwh, p.export_eur_kwh, data.house_kwh, data.pv_kwh, battery_kwh))
    base = sum(slot_cost(i, e, h, v, 0.0) for i, e, h, v in
               zip(p.import_eur_kwh, p.export_eur_kwh, data.house_kwh, data.pv_kwh))
    return Account(cost, base, soc_delta_kwh)


Forecast = tuple[Mapping[datetime, float], Mapping[datetime, float]]      # (base load kWh, PV kWh) per quarter start (UTC)


def run_replay(data: ReplayData, cfg: BatteryConfig, tz: ZoneInfo = LOCAL_TZ, publish_hour: int = 13,
               peaks: Mapping[date, float] | None = None, forecasts: Callable[[datetime], Forecast | None] | None = None) -> ReplayResult:
    """Walk the quarters; each step plans with the prices known then, executes one quarter on the fake battery.

    `peaks` (hems.terminal.daily_peaks of a price series that reaches further back than the replay) values the energy kept past the horizon
    with the typical peak of the days before each quarter's day, as the live planner does; without it the default terminal value is used.

    `forecasts(start)` returns the load and PV forecast the planner would have had at that quarter (None: use the recorded load and PV, an oracle).
    Planning uses the forecast; the simulated battery and the accounting always use what really happened, so forecast errors cost what they cost."""
    starts = data.prices.starts
    load = dict(zip(starts, data.house_kwh))
    pv = dict(zip(starts, data.pv_kwh))
    limits = BatteryLimits(cfg.capacity_kwh, cfg.max_power_kw * 1000, cfg.max_power_kw * 1000)
    battery = FakeBattery(limits, starts[0], data.soc0_kwh / cfg.capacity_kwh * 100, cfg.round_trip_eff, cfg.hard_min_soc * 100)
    result, previous = ReplayResult(), None
    for index, start in enumerate(starts):
        horizon = int((known_until(start, tz, publish_hour) - start) / QUARTER)
        soc = battery.soc_pct / 100 * cfg.capacity_kwh
        history_peak = reference_peak(peaks, start.astimezone(tz).date()) if peaks else None
        expected = forecasts(start) if forecasts else None
        plan_load, plan_pv = expected if expected else (load, pv)
        decision = plan_next(HorizonInputs(start, soc, data.prices, plan_load, plan_pv, max_slots=horizon, history_peak=history_peak), cfg)
        command = decision.command if decision else None
        battery.apply([command] if command else [])
        battery.advance(QUARTER)
        flow_kwh = battery.status().power_w.value * SLOT_H / 1000
        if decision:
            shift = plan_shift(previous, decision)
            if shift:
                result.shifts.append(shift)
            decision.trace["executed_w"] = round(battery.status().power_w.value)
            result.decisions.append(decision)
            previous = decision
        result.battery_kwh.append(flow_kwh)
        result.soc_kwh.append(battery.soc_pct / 100 * cfg.capacity_kwh)
    return result
