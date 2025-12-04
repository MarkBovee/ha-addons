"""Price-aware charging window planner."""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import List, Optional
from zoneinfo import ZoneInfo

from shared.ha_api import HomeAssistantApi

logger = logging.getLogger(__name__)


@dataclass
class ChargingWindow:
    """Represents a planned charging window in local time."""

    start: datetime
    end: datetime
    total_price: float
    slot_count: int
    target_date: date
    price_hash: str


@dataclass
class PlanResult:
    """Planner outcome."""

    status: str
    message: str
    window: Optional[ChargingWindow]
    curve_points: int


class PriceWindowPlanner:
    """Selects the cheapest contiguous charging window from a price curve."""

    SLOT_MINUTES = 15

    def __init__(
        self,
        ha_api: HomeAssistantApi,
        price_entity_id: str,
        required_minutes: int,
        earliest_hour: int,
        latest_hour: int,
        timezone_name: str,
        safety_margin_minutes: int = 0,
    ) -> None:
        self._ha_api = ha_api
        self._entity_id = price_entity_id
        self._required_minutes = max(required_minutes, self.SLOT_MINUTES)
        self._earliest_hour = max(0, min(earliest_hour, 23))
        self._latest_hour = max(0, min(latest_hour, 23))
        self._tz = ZoneInfo(timezone_name)
        self._safety_margin = max(0, safety_margin_minutes)

        if self._latest_hour <= self._earliest_hour:
            logger.warning(
                "latest_end_hour (%s) must be greater than earliest_start_hour (%s). Adjusting to +1 hour.",
                self._latest_hour,
                self._earliest_hour,
            )
            self._latest_hour = min(23, self._earliest_hour + 1)

        if self._required_minutes % self.SLOT_MINUTES != 0:
            rounded = ((self._required_minutes // self.SLOT_MINUTES) + 1) * self.SLOT_MINUTES
            logger.warning(
                "required_minutes_per_day (%s) must be a multiple of 15. Rounding up to %s minutes.",
                self._required_minutes,
                rounded,
            )
            self._required_minutes = rounded

    def compute_plan(self, now: Optional[datetime] = None) -> PlanResult:
        """Compute the optimal charging window.

        Returns a PlanResult with status:
        - "scheduled": plan ready
        - "waiting_for_prices": tomorrow curve missing
        - "insufficient_window": not enough slots within window
        - "price_sensor_missing": entity missing or malformed
        """

        local_now = (now or datetime.utcnow().replace(tzinfo=ZoneInfo("UTC"))).astimezone(self._tz)
        target_date = local_now.date() + timedelta(days=1)

        state = self._ha_api.get_entity_state(self._entity_id)
        if not state or "attributes" not in state:
            return PlanResult(
                status="price_sensor_missing",
                message=f"Entity {self._entity_id} not found",
                window=None,
                curve_points=0,
            )

        price_curve = state["attributes"].get("price_curve") or []
        if not price_curve:
            return PlanResult(
                status="price_sensor_missing",
                message=f"Entity {self._entity_id} has no price_curve attribute",
                window=None,
                curve_points=0,
            )

        intervals = self._normalize_intervals(price_curve)
        day_intervals = [p for p in intervals if p.start.date() == target_date]

        if not day_intervals:
            return PlanResult(
                status="waiting_for_prices",
                message=f"No price data for {target_date.isoformat()}",
                window=None,
                curve_points=len(intervals),
            )

        window_start = datetime.combine(target_date, time(hour=self._earliest_hour), self._tz)
        window_end = datetime.combine(target_date, time(hour=self._latest_hour), self._tz)

        eligible = [p for p in day_intervals if p.start >= window_start and p.end <= window_end]
        required_slots = self._required_minutes // self.SLOT_MINUTES

        if len(eligible) < required_slots:
            return PlanResult(
                status="insufficient_window",
                message="Not enough price slots inside configured window",
                window=None,
                curve_points=len(day_intervals),
            )

        best_indices = self._find_best_window(eligible, required_slots)
        if best_indices is None:
            return PlanResult(
                status="insufficient_window",
                message="No contiguous slots available",
                window=None,
                curve_points=len(day_intervals),
            )

        start_idx, end_idx, best_total = best_indices
        selected_slots = eligible[start_idx:end_idx]
        start_dt = selected_slots[0].start
        end_dt = selected_slots[-1].end

        margin = timedelta(minutes=self._safety_margin)
        adjusted_start = max(start_dt - margin, window_start)
        adjusted_end = min(end_dt + margin, window_end)

        price_hash = self._hash_slots(selected_slots)
        window = ChargingWindow(
            start=adjusted_start,
            end=adjusted_end,
            total_price=best_total,
            slot_count=len(selected_slots),
            target_date=target_date,
            price_hash=price_hash,
        )

        return PlanResult(
            status="scheduled",
            message="Cheapest window selected",
            window=window,
            curve_points=len(day_intervals),
        )

    def _normalize_intervals(self, raw_curve: List[dict]) -> List[_PriceInterval]:
        normalized: List[_PriceInterval] = []
        for item in raw_curve:
            try:
                start = self._parse_ts(item.get("start"))
                end = self._parse_ts(item.get("end"))
                price = float(item.get("price"))
            except Exception as exc:
                logger.debug("Skipping malformed price entry %s: %s", item, exc)
                continue

            normalized.append(_PriceInterval(start=start, end=end, price=price))

        normalized.sort(key=lambda interval: interval.start)
        return normalized

    def _parse_ts(self, value: Optional[str]) -> datetime:
        if not value:
            raise ValueError("Missing timestamp")
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=self._tz)
        return dt.astimezone(self._tz)

    def _find_best_window(self, intervals: List[_PriceInterval], slots: int):
        prices = [i.price for i in intervals]
        window_sum = sum(prices[:slots])
        best_total = window_sum
        best_range = (0, slots, best_total)

        for start_idx in range(1, len(intervals) - slots + 1):
            window_sum += prices[start_idx + slots - 1] - prices[start_idx - 1]
            if window_sum < best_total - 1e-9 or (
                abs(window_sum - best_total) <= 1e-9 and intervals[start_idx].start < intervals[best_range[0]].start
            ):
                best_total = window_sum
                best_range = (start_idx, start_idx + slots, best_total)

        return best_range

    def _hash_slots(self, intervals: List[_PriceInterval]) -> str:
        payload = "|".join(f"{slot.start.isoformat()}:{slot.price}" for slot in intervals)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass
class _PriceInterval:
    start: datetime
    end: datetime
    price: float
