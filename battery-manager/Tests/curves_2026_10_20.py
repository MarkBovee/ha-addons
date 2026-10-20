"""Real 15-minute prices of 2026-10-20 (Europe/Amsterdam, CEST), as battery-manager read them from the energy-prices sensors.

The night was flat at 0.33-0.34 and the morning sale (07:30-09:30, export 0.43-0.46, about 0.443) is thin: after the margin gate
dropped the night charge the battery stood at 49.8% at 05:30. The pre-sell check then bought 2.7 kWh at 0.337 (05:30) and again
1 kWh at 0.387 (07:00) for that sale, 0.443 x 0.9 - 0.337 = 0.062 and 0.443 x 0.9 - 0.387 = 0.012 per kWh. Prices are EUR/kWh,
one value per quarter from 00:00 local.
"""

from datetime import datetime, timedelta, timezone
from typing import Dict, List

CEST = timezone(timedelta(hours=2))

IMPORT_QUARTERS: List[float] = [
    0.3334, 0.3329, 0.3347, 0.3321, 0.3260, 0.3292, 0.3317, 0.3283,
    0.3401, 0.3362, 0.3352, 0.3349, 0.3362, 0.3343, 0.3338, 0.3327,
    0.3401, 0.3401, 0.3379, 0.3388, 0.3327, 0.3322, 0.3367, 0.3403,
    0.3388, 0.3565, 0.3724, 0.3863, 0.3870, 0.3983, 0.4037, 0.4081,
    0.4311, 0.4263, 0.4165, 0.4020, 0.4234, 0.4075, 0.3704, 0.3455,
    0.3485, 0.3269, 0.3111, 0.3124, 0.2796, 0.2627, 0.2609, 0.2579,
    0.2517, 0.2537, 0.2433, 0.2543, 0.2517, 0.2659, 0.2694, 0.2734,
    0.2555, 0.2653, 0.2856, 0.3220, 0.3017, 0.3252, 0.3428, 0.3712,
    0.3488, 0.3777, 0.3977, 0.4077, 0.3986, 0.4141, 0.4332, 0.4390,
    0.4377, 0.4432, 0.4425, 0.4526, 0.4444, 0.4335, 0.4214, 0.4334,
    0.4173, 0.4209, 0.4256, 0.4254, 0.4205, 0.4084, 0.3979, 0.3559,
    0.3903, 0.3847, 0.3729, 0.3716, 0.3848, 0.3751, 0.3721, 0.3571,
]

EXPORT_QUARTERS: List[float] = [
    0.3537, 0.3531, 0.3551, 0.3522, 0.3455, 0.3490, 0.3518, 0.3481,
    0.3610, 0.3567, 0.3557, 0.3553, 0.3567, 0.3546, 0.3541, 0.3529,
    0.3610, 0.3610, 0.3586, 0.3596, 0.3529, 0.3523, 0.3573, 0.3612,
    0.3596, 0.3791, 0.3965, 0.4118, 0.4126, 0.4250, 0.4310, 0.4358,
    0.4611, 0.4559, 0.4451, 0.4291, 0.4527, 0.4351, 0.3944, 0.3670,
    0.3703, 0.3465, 0.3292, 0.3305, 0.2944, 0.2759, 0.2739, 0.2706,
    0.2638, 0.2659, 0.2545, 0.2666, 0.2638, 0.2794, 0.2832, 0.2876,
    0.2679, 0.2787, 0.3011, 0.3411, 0.3188, 0.3446, 0.3640, 0.3952,
    0.3706, 0.4024, 0.4243, 0.4354, 0.4254, 0.4424, 0.4635, 0.4699,
    0.4684, 0.4744, 0.4737, 0.4848, 0.4757, 0.4637, 0.4504, 0.4636,
    0.4459, 0.4499, 0.4551, 0.4548, 0.4495, 0.4362, 0.4246, 0.3784,
    0.4162, 0.4101, 0.3971, 0.3957, 0.4102, 0.3996, 0.3963, 0.3797,
]


def _curve(prices: List[float]) -> List[Dict[str, object]]:
    """Quarter entries (start, end, price) for the day, in the format of the price sensors' price_curve attribute."""
    first = datetime(2026, 10, 20, 0, 0, tzinfo=CEST)
    return [
        {"start": (first + timedelta(minutes=15 * i)).isoformat(), "end": (first + timedelta(minutes=15 * (i + 1))).isoformat(), "price": price}
        for i, price in enumerate(prices)
    ]


def import_curve() -> List[Dict[str, object]]:
    """Consumer import price curve of 2026-10-20."""
    return _curve(IMPORT_QUARTERS)


def export_curve() -> List[Dict[str, object]]:
    """Consumer export price curve of 2026-10-20."""
    return _curve(EXPORT_QUARTERS)
