"""In-memory implementations of the contracts, for tests and dry-run simulation.

They behave like a plausible device (limits, losses, a device-level SoC protection, a sensor that can freeze),
so planner and rolling-horizon tests exercise the contract boundary instead of mocking internals.
"""
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Sequence

from hems.contracts import (BatteryCommand, BatteryLimits, BatteryStatus, CommandResult, GridStatus,
                            HouseLoadStatus, MarketPrices, PvStatus, Reading)


def _reading(value: float | None, observed_at: datetime) -> Reading | None:
    """Wrap a value as a reading, or None when the fake source is 'unavailable'."""
    return None if value is None else Reading(value, observed_at)


@dataclass
class FakeBattery:
    """Battery with losses and limits. `advance` assumes the active command is constant over the step, so step
    in quarters. A real device clamps requests too; the fake reports what it actually did in `power_w`."""
    limits: BatteryLimits
    now: datetime
    soc_pct: float
    round_trip_eff: float = 0.82
    device_min_soc_pct: float = 5.0          # device protection, independent of any HEMS reserve
    frozen: bool = False                     # sensor stopped updating: readings keep their old observed_at
    received: list[BatteryCommand] = field(default_factory=list)
    _active: list[BatteryCommand] = field(default_factory=list)
    _power_w: float = 0.0
    _observed_at: datetime | None = None

    def status(self) -> BatteryStatus:
        """Current SoC and power as readings (stamped with the last non-frozen update)."""
        at = self._observed_at or self.now
        return BatteryStatus(self.limits, Reading(self.soc_pct, at), Reading(self._power_w, at))

    def apply(self, commands: Sequence[BatteryCommand]) -> CommandResult:
        """Accept the plan's next quarters; they replace whatever was active before."""
        self.received.extend(commands)
        self._active = list(commands)
        return CommandResult(True)

    def advance(self, step: timedelta) -> None:
        """Run the active command for `step`, clamped by power limits, capacity and the device minimum SoC."""
        hours = step.total_seconds() / 3600
        eff = self.round_trip_eff ** 0.5
        cap = self.limits.usable_capacity_kwh
        requested = next((c.power_w for c in self._active if c.start <= self.now < c.end), 0.0)
        if requested >= 0:
            ac_w = min(requested, self.limits.max_charge_w)
            dsoc_kwh = min(ac_w / 1000 * hours * eff, (100 - self.soc_pct) / 100 * cap)
            self._power_w = dsoc_kwh / eff / hours * 1000 if hours else 0.0
        else:
            ac_w = min(-requested, self.limits.max_discharge_w)
            dsoc_kwh = -min(ac_w / 1000 * hours / eff, max(self.soc_pct - self.device_min_soc_pct, 0.0) / 100 * cap)
            self._power_w = dsoc_kwh * eff / hours * 1000 if hours else 0.0
        self.soc_pct += dsoc_kwh / cap * 100
        self.now += step
        if not self.frozen:
            self._observed_at = self.now


@dataclass
class FakeGrid:
    power_w: float | None
    observed_at: datetime

    def status(self) -> GridStatus:
        """The configured grid reading."""
        return GridStatus(_reading(self.power_w, self.observed_at))


@dataclass
class FakePv:
    power_w: float | None
    observed_at: datetime

    def status(self) -> PvStatus:
        """The configured PV reading."""
        return PvStatus(_reading(self.power_w, self.observed_at))


@dataclass
class FakeHouseLoad:
    power_w: float | None
    observed_at: datetime

    def status(self) -> HouseLoadStatus:
        """The configured house-load reading."""
        return HouseLoadStatus(_reading(self.power_w, self.observed_at))


@dataclass
class FixedMarketPrices:
    """Market price source that always returns the series it was given."""
    series: MarketPrices | None

    def prices(self, now: datetime) -> MarketPrices | None:
        """The fixed series, regardless of `now`."""
        return self.series
