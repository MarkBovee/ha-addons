"""Weather source contract and Open-Meteo parsing (pure; the HTTP call lives in the HA layer).

Open-Meteo labels a quarter-hour value with the END of the interval it averages (mean of the preceding 15 minutes),
so series are re-keyed by quarter start before anything else sees them. Times are requested in UTC.
"""
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Mapping

from hems.pvforecast import preceding_mean_to_start

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"


@dataclass(frozen=True)
class Weather:
    """Irradiance (W/m2) and outdoor temperature (C), keyed by quarter start (UTC)."""
    ghi_w_m2: Mapping[datetime, float]
    temperature_c: Mapping[datetime, float]
    fetched_at: datetime


def open_meteo_params(latitude: float, longitude: float, past_days: int = 7, forecast_days: int = 2) -> dict[str, str | int | float]:
    """Query parameters for the quarter-hour radiation and temperature series, in UTC.

    The coordinates are rounded to two decimals (about 1 km): enough for weather, and the exact home location
    does not leave the installation."""
    return {"latitude": round(latitude, 2), "longitude": round(longitude, 2), "minutely_15": "shortwave_radiation,temperature_2m",
            "past_days": past_days, "forecast_days": forecast_days, "timezone": "UTC"}


def _series(block: Mapping[str, list], name: str) -> dict[datetime, float]:
    """One minutely_15 variable as {interval end (UTC): value}, skipping gaps (null values)."""
    return {datetime.fromisoformat(t).replace(tzinfo=timezone.utc): v for t, v in zip(block["time"], block[name]) if v is not None}


def parse_open_meteo(payload: Mapping, fetched_at: datetime) -> Weather:
    """Weather from an Open-Meteo response; raises KeyError/ValueError on an unexpected shape (fail fast)."""
    block = payload["minutely_15"]
    return Weather(preceding_mean_to_start(_series(block, "shortwave_radiation")),
                   preceding_mean_to_start(_series(block, "temperature_2m")), fetched_at)
