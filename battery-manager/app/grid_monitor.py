"""Grid import/export monitoring helpers."""

from __future__ import annotations

from typing import Optional


def is_exporting(grid_power: Optional[float], threshold: float) -> bool:
    """Return True when grid export is detected (negative power below threshold)."""

    if grid_power is None:
        return False
    return grid_power < -abs(threshold)


def should_reduce_discharge(grid_power: Optional[float], threshold: float) -> bool:
    """Return True when discharge should be reduced due to export."""

    return is_exporting(grid_power, threshold)
