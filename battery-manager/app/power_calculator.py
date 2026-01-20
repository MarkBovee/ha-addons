"""Power scaling helpers for discharge periods."""

from __future__ import annotations


def calculate_scaled_power(rank: int, max_power: int, min_power: int) -> int:
    """Scale discharge power based on period rank.

    Uses formula: max(max_power / rank, min_power).
    """

    if rank <= 0:
        raise ValueError("rank must be a positive integer")
    if max_power <= 0 or min_power <= 0:
        raise ValueError("power values must be positive")

    scaled = int(max_power / rank)
    return max(scaled, min_power)
