"""State-of-charge protection helpers."""

from __future__ import annotations

from datetime import datetime, time
from typing import Union

TimeLike = Union[datetime, time]


def can_charge(soc: float, max_soc: float) -> bool:
    """Return True if charging is allowed based on max SOC."""

    return soc < max_soc


def can_discharge(soc: float, min_soc: float, conservative_soc: float, is_conservative: bool) -> bool:
    """Return True if discharging is allowed under SOC rules."""

    if soc <= min_soc:
        return False
    if is_conservative and soc < conservative_soc:
        return False
    return True


def should_target_eod(current_time: TimeLike, eod_time: time, target_soc: float) -> bool:
    """Return True when end-of-day SOC target should be enforced."""

    if isinstance(current_time, datetime):
        current = current_time.time()
    else:
        current = current_time

    _ = target_soc
    return current >= eod_time
