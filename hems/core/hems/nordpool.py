"""Nord Pool day-ahead prices: request parameters, parsing and the refresh policy (pure; HTTP lives in the HA layer).

The public data portal answers with 96 quarter-hour entries per delivery day (CET date); tomorrow's day is
HTTP 204 until it is published, around 13:00 local. Prices are EUR/MWh in the payload and EUR/kWh everywhere else.
"""
from datetime import date, datetime, timedelta, timezone
from typing import Iterable, Mapping, Sequence
from zoneinfo import ZoneInfo

from hems.contracts import MarketPrices
from hems.slots import SLOT_MINUTES

NORD_POOL_URL = "https://dataportal-api.nordpoolgroup.com/api/DayAheadPrices"
# The public portal only answers requests that look like its own web app; the same headers the energy-prices add-on sends.
NORD_POOL_HEADERS = {"Origin": "https://data.nordpoolgroup.com", "Referer": "https://data.nordpoolgroup.com/"}
DELIVERY_TZ = ZoneInfo("Europe/Amsterdam")          # delivery days are CET dates
PUBLISH_HOUR = 13                                    # tomorrow is expected from this local hour
RETRY_AFTER = timedelta(minutes=10)


def nordpool_params(delivery_date: date, area: str = "NL", currency: str = "EUR") -> dict[str, str]:
    """Query parameters for one delivery day."""
    return {"date": delivery_date.isoformat(), "market": "DayAhead", "deliveryArea": area, "currency": currency}


def parse_day_ahead(payload: Mapping, area: str = "NL") -> dict[datetime, float]:
    """{quarter start (UTC): EUR/kWh} from a day-ahead payload; entries without a price for the area are skipped.

    Raises KeyError when the payload has no `multiAreaEntries` (fail fast on an unexpected shape)."""
    prices: dict[datetime, float] = {}
    for entry in payload["multiAreaEntries"]:
        value = (entry.get("entryPerArea") or {}).get(area)
        if value is None:
            continue
        start = datetime.fromisoformat(entry["deliveryStart"].replace("Z", "+00:00")).astimezone(timezone.utc)
        prices[start] = float(value) / 1000
    return prices


def merge_days(days: Sequence[Mapping[datetime, float]], fetched_at: datetime) -> MarketPrices | None:
    """One sorted market series from several delivery days; None when there is no price at all."""
    merged: dict[datetime, float] = {}
    for day in days:
        merged.update(day)
    if not merged:
        return None
    starts = tuple(sorted(merged))
    return MarketPrices(starts, tuple(merged[s] for s in starts), fetched_at)


def wanted_until(now: datetime) -> datetime:
    """End (UTC) of the delivery days that should be known at `now`: today, plus tomorrow from the publication hour."""
    local = now.astimezone(DELIVERY_TZ)
    midnight = (local + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return (midnight + timedelta(days=1) if local.hour >= PUBLISH_HOUR else midnight).astimezone(timezone.utc)


def delivery_dates(now: datetime) -> list[date]:
    """Delivery dates to request at `now`: today, plus tomorrow from the publication hour."""
    local = now.astimezone(DELIVERY_TZ)
    return [local.date()] + ([local.date() + timedelta(days=1)] if local.hour >= PUBLISH_HOUR else [])


def tomorrow_quarters(starts: Iterable[datetime], now: datetime) -> int:
    """How many of the given quarter starts fall in tomorrow's delivery day (0 until it is published)."""
    local = now.astimezone(DELIVERY_TZ)
    first = (local + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    last = first + timedelta(days=1)
    return sum(1 for s in starts if first <= s.astimezone(DELIVERY_TZ) < last)


def fetch_due(now: datetime, market: MarketPrices | None, last_attempt: datetime | None) -> bool:
    """True when the known prices end before what should be known at `now`, at most once per RETRY_AFTER."""
    if last_attempt is not None and now - last_attempt < RETRY_AFTER:
        return False
    covered = market.covers_until() if market else None
    return covered is None or covered < wanted_until(now)
