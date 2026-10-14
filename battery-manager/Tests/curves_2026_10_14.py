"""Real 15-minute prices of 2026-10-14 (Europe/Amsterdam, CEST), as battery-manager read them from the energy-prices sensors.

On this day the morning peak (08:00-10:00, export up to 0.62) lies before the cheapest midday window (11:45-15:45) and is
higher than the evening peak (export up to 0.52). With discharge_after_charge_only the plan sold only in the evening and
the morning peak was missed (incident of 2026-10-14). Prices are EUR/kWh, one value per quarter from 00:00 local.
"""

from datetime import datetime, timedelta, timezone
from typing import Dict, List

CEST = timezone(timedelta(hours=2))

IMPORT_QUARTERS: List[float] = [
    0.2739, 0.2688, 0.2688, 0.2618, 0.2833, 0.2839, 0.2820, 0.2831,
    0.2809, 0.2988, 0.2959, 0.3172, 0.3315, 0.3398, 0.3313, 0.3563,
    0.3272, 0.3448, 0.3614, 0.3730, 0.3311, 0.3500, 0.3534, 0.3789,
    0.3488, 0.3729, 0.3835, 0.3949, 0.3808, 0.4093, 0.4341, 0.5271,
    0.4740, 0.5379, 0.5351, 0.4803, 0.5761, 0.4332, 0.4071, 0.3749,
    0.3949, 0.3738, 0.3807, 0.3715, 0.3545, 0.3138, 0.2978, 0.2848,
    0.2814, 0.2695, 0.2637, 0.2560, 0.2603, 0.2520, 0.2460, 0.2373,
    0.2471, 0.2517, 0.2571, 0.2665, 0.2587, 0.2719, 0.2875, 0.3073,
    0.3021, 0.3246, 0.3672, 0.3981, 0.3695, 0.3960, 0.4150, 0.4491,
    0.4334, 0.4438, 0.4641, 0.4980, 0.4785, 0.4902, 0.4926, 0.4926,
    0.4842, 0.4688, 0.4441, 0.4332, 0.4517, 0.4256, 0.4169, 0.3968,
    0.4087, 0.3908, 0.3767, 0.3667, 0.3833, 0.3715, 0.3647, 0.3606,
]

EXPORT_QUARTERS: List[float] = [
    0.2882, 0.2826, 0.2826, 0.2749, 0.2986, 0.2992, 0.2971, 0.2983,
    0.2959, 0.3156, 0.3124, 0.3358, 0.3515, 0.3607, 0.3514, 0.3788,
    0.3469, 0.3662, 0.3844, 0.3972, 0.3511, 0.3719, 0.3756, 0.4037,
    0.3706, 0.3971, 0.4088, 0.4213, 0.4058, 0.4371, 0.4644, 0.5668,
    0.5083, 0.5786, 0.5755, 0.5152, 0.6207, 0.4635, 0.4347, 0.3993,
    0.4213, 0.3981, 0.4057, 0.3956, 0.3768, 0.3321, 0.3145, 0.3002,
    0.2964, 0.2834, 0.2770, 0.2685, 0.2733, 0.2641, 0.2576, 0.2480,
    0.2588, 0.2638, 0.2697, 0.2801, 0.2715, 0.2860, 0.3032, 0.3249,
    0.3192, 0.3439, 0.3908, 0.4249, 0.3933, 0.4225, 0.4434, 0.4809,
    0.4636, 0.4750, 0.4974, 0.5347, 0.5132, 0.5262, 0.5288, 0.5288,
    0.5195, 0.5026, 0.4754, 0.4635, 0.4838, 0.4551, 0.4455, 0.4234,
    0.4364, 0.4167, 0.4013, 0.3903, 0.4085, 0.3956, 0.3881, 0.3836,
]


def _curve(prices: List[float]) -> List[Dict[str, object]]:
    """Quarter entries (start, end, price) for the day, in the format of the price sensors' price_curve attribute."""
    first = datetime(2026, 10, 14, 0, 0, tzinfo=CEST)
    return [
        {"start": (first + timedelta(minutes=15 * i)).isoformat(), "end": (first + timedelta(minutes=15 * (i + 1))).isoformat(), "price": price}
        for i, price in enumerate(prices)
    ]


def import_curve() -> List[Dict[str, object]]:
    """Consumer import price curve of 2026-10-14."""
    return _curve(IMPORT_QUARTERS)


def export_curve() -> List[Dict[str, object]]:
    """Consumer export price curve of 2026-10-14."""
    return _curve(EXPORT_QUARTERS)
