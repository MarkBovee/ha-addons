"""Real 15-minute prices of 2026-10-15 (Europe/Amsterdam, CEST), as battery-manager read them from the energy-prices sensors.

The morning peak (07:15-09:30, export 0.45-0.50) is thin: charging at 0.33 for it earns about 0.08 per kWh against the grid
charge margin, and the evening peak (17:30-19:30, up to 0.49) follows the midday window. On this day a battery at 74 % SoC was
charged to 100 % at 04:15 for the morning sale (incident of 2026-10-15). Prices are EUR/kWh, one value per quarter from 00:00 local.
"""

from datetime import datetime, timedelta, timezone
from typing import Dict, List

CEST = timezone(timedelta(hours=2))

IMPORT_QUARTERS: List[float] = [
    0.3782, 0.3657, 0.3574, 0.3553, 0.3784, 0.3551, 0.3520, 0.3456,
    0.3497, 0.3404, 0.3453, 0.3373, 0.3363, 0.3442, 0.3392, 0.3350,
    0.3397, 0.3323, 0.3346, 0.3343, 0.3343, 0.3395, 0.3477, 0.3617,
    0.3582, 0.3729, 0.4029, 0.4157, 0.4107, 0.4197, 0.4312, 0.4413,
    0.4657, 0.4568, 0.4404, 0.4137, 0.4334, 0.4213, 0.3819, 0.3512,
    0.3968, 0.3790, 0.3591, 0.3364, 0.3367, 0.3226, 0.3015, 0.2886,
    0.2828, 0.2615, 0.2498, 0.2433, 0.2437, 0.2385, 0.2314, 0.2314,
    0.2313, 0.2364, 0.2445, 0.2514, 0.2508, 0.2681, 0.2895, 0.3028,
    0.3011, 0.3237, 0.3512, 0.3847, 0.3732, 0.4087, 0.4181, 0.4323,
    0.4222, 0.4260, 0.4365, 0.4546, 0.4502, 0.4434, 0.4095, 0.3925,
    0.4004, 0.3972, 0.3897, 0.3729, 0.4153, 0.3971, 0.3774, 0.3532,
    0.3926, 0.3796, 0.3727, 0.3702, 0.3751, 0.3684, 0.3691, 0.3519,
]

EXPORT_QUARTERS: List[float] = [
    0.4029, 0.3892, 0.3800, 0.3778, 0.4032, 0.3775, 0.3742, 0.3671,
    0.3716, 0.3614, 0.3667, 0.3579, 0.3569, 0.3655, 0.3600, 0.3554,
    0.3606, 0.3525, 0.3550, 0.3546, 0.3546, 0.3603, 0.3694, 0.3848,
    0.3809, 0.3971, 0.4301, 0.4442, 0.4387, 0.4486, 0.4612, 0.4724,
    0.4991, 0.4894, 0.4713, 0.4420, 0.4636, 0.4503, 0.4070, 0.3732,
    0.4234, 0.4038, 0.3819, 0.3570, 0.3573, 0.3418, 0.3185, 0.3044,
    0.2980, 0.2746, 0.2617, 0.2545, 0.2550, 0.2493, 0.2415, 0.2415,
    0.2413, 0.2469, 0.2558, 0.2634, 0.2628, 0.2818, 0.3053, 0.3200,
    0.3181, 0.3430, 0.3732, 0.4101, 0.3974, 0.4364, 0.4468, 0.4624,
    0.4514, 0.4555, 0.4671, 0.4870, 0.4821, 0.4746, 0.4374, 0.4186,
    0.4274, 0.4238, 0.4156, 0.3971, 0.4438, 0.4237, 0.4021, 0.3755,
    0.4187, 0.4045, 0.3969, 0.3941, 0.3996, 0.3921, 0.3929, 0.3740,
]


def _curve(prices: List[float]) -> List[Dict[str, object]]:
    """Quarter entries (start, end, price) for the day, in the format of the price sensors' price_curve attribute."""
    first = datetime(2026, 10, 15, 0, 0, tzinfo=CEST)
    return [
        {"start": (first + timedelta(minutes=15 * i)).isoformat(), "end": (first + timedelta(minutes=15 * (i + 1))).isoformat(), "price": price}
        for i, price in enumerate(prices)
    ]


def import_curve() -> List[Dict[str, object]]:
    """Consumer import price curve of 2026-10-15."""
    return _curve(IMPORT_QUARTERS)


def export_curve() -> List[Dict[str, object]]:
    """Consumer export price curve of 2026-10-15."""
    return _curve(EXPORT_QUARTERS)
