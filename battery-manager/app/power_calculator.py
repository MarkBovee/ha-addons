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


def calculate_rank_scaled_power(rank: int, top_x: int, max_power: int, min_power: int) -> int:
    """Scale power linearly by rank within the top X periods.

    Rank 1 (best) => max_power
    Rank top_x (worst) => min_power
    """

    if rank <= 0:
        raise ValueError("rank must be a positive integer")
    if top_x <= 0:
        raise ValueError("top_x must be a positive integer")
    if max_power <= 0 or min_power <= 0:
        raise ValueError("power values must be positive")

    if top_x == 1:
        scaled = max_power
    else:
        power_percentage = (top_x - rank) / float(top_x - 1)
        power_percentage = max(0.0, min(1.0, power_percentage))
        scaled = int(min_power + (max_power - min_power) * power_percentage)

    rounded = int(round(scaled / 1000.0)) * 1000
    return max(min(rounded, max_power), min_power)
