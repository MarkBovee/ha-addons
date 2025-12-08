"""Simple price slot analyzer - identifies cheapest charging slots."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional
from zoneinfo import ZoneInfo

from shared.ha_api import HomeAssistantApi

logger = logging.getLogger(__name__)


@dataclass
class PriceSlot:
    """A single price slot (15-minute interval)."""
    
    start: datetime
    end: datetime
    price: float
    rank: int  # 1 = cheapest


@dataclass
class DailyPriceAnalysis:
    """Analysis result for a day's prices."""
    
    target_date: date
    all_slots: List[PriceSlot]
    cheapest_slots: List[PriceSlot]
    min_price: float
    max_price: float
    avg_price: float
    price_threshold: Optional[float] = None  # EUR/kWh threshold used
    slots_filtered_by_threshold: int = 0  # Count of slots excluded by threshold
    
    @property
    def slot_count(self) -> int:
        return len(self.cheapest_slots)
    
    @property
    def threshold_active(self) -> bool:
        """Returns True if threshold filtering excluded any slots."""
        return self.slots_filtered_by_threshold > 0
    
    def is_in_cheapest(self, dt: datetime) -> bool:
        """Check if a datetime falls within one of the cheapest slots."""
        for slot in self.cheapest_slots:
            if slot.start <= dt < slot.end:
                return True
        return False
    
    def get_rank(self, dt: datetime) -> Optional[int]:
        """Get the rank of the slot containing the given datetime."""
        for slot in self.cheapest_slots:
            if slot.start <= dt < slot.end:
                return slot.rank
        return None


class PriceSlotAnalyzer:
    """Analyzes price data and identifies cheapest slots for charging."""
    
    SLOT_MINUTES = 15
    
    def __init__(
        self,
        ha_api: HomeAssistantApi,
        price_entity_id: str,
        timezone_name: str,
        top_x_count: int = 16,
        price_threshold: Optional[float] = None,
    ) -> None:
        """
        Initialize the analyzer.
        
        Args:
            ha_api: Home Assistant API client
            price_entity_id: Entity ID of the price sensor (e.g., sensor.energy_prices_electricity_import_price)
            timezone_name: Timezone for local time conversions
            top_x_count: Number of unique price levels to select (default 16)
            price_threshold: Max price in EUR/kWh (None = no threshold)
        """
        self._ha_api = ha_api
        self._entity_id = price_entity_id
        self._tz = ZoneInfo(timezone_name)
        self._top_x_count = max(1, top_x_count)
        self._price_threshold = price_threshold
    
    def analyze_today(self) -> Optional[DailyPriceAnalysis]:
        """Analyze today's prices and return the cheapest slots."""
        local_now = datetime.now(self._tz)
        return self._analyze_date(local_now.date())
    
    def analyze_tomorrow(self) -> Optional[DailyPriceAnalysis]:
        """Analyze tomorrow's prices and return the cheapest slots."""
        local_now = datetime.now(self._tz)
        return self._analyze_date(local_now.date() + timedelta(days=1))
    
    def get_price_curve(self) -> Optional[List[Dict]]:
        """Fetch the raw price curve from the HA sensor."""
        state = self._ha_api.get_entity_state(self._entity_id)
        if not state or "attributes" not in state:
            logger.warning("Price sensor %s not found or has no attributes", self._entity_id)
            return None
        
        price_curve = state["attributes"].get("price_curve") or []
        if not price_curve:
            logger.warning("Price sensor %s has no price_curve attribute", self._entity_id)
            return None
        
        return price_curve
    
    def _analyze_date(self, target_date: date) -> Optional[DailyPriceAnalysis]:
        """Analyze prices for a specific date."""
        price_curve = self.get_price_curve()
        if not price_curve:
            return None
        
        # Parse and filter slots for the target date
        day_slots = self._parse_slots_for_date(price_curve, target_date)
        
        if not day_slots:
            logger.info("No price data available for %s", target_date.isoformat())
            return None
        
        # Apply price threshold filter if set
        slots_filtered_count = 0
        if self._price_threshold is not None:
            eligible_slots = [s for s in day_slots if s.price <= self._price_threshold]
            slots_filtered_count = len(day_slots) - len(eligible_slots)
            if slots_filtered_count > 0:
                logger.debug(
                    "Price threshold %.2f EUR/kWh filtered out %d of %d slots for %s",
                    self._price_threshold,
                    slots_filtered_count,
                    len(day_slots),
                    target_date.isoformat(),
                )
        else:
            eligible_slots = day_slots
        
        # Handle case where no slots meet threshold
        if not eligible_slots:
            logger.info(
                "No slots below price threshold %.2f EUR/kWh for %s",
                self._price_threshold,
                target_date.isoformat(),
            )
            # Return analysis with empty cheapest_slots but full stats
            all_prices = [s.price for s in day_slots]
            return DailyPriceAnalysis(
                target_date=target_date,
                all_slots=sorted(day_slots, key=lambda s: s.start),
                cheapest_slots=[],
                min_price=min(all_prices),
                max_price=max(all_prices),
                avg_price=sum(all_prices) / len(all_prices),
                price_threshold=self._price_threshold,
                slots_filtered_by_threshold=slots_filtered_count,
            )
        
        # Get unique prices sorted ascending (from eligible slots only)
        unique_prices = sorted(set(s.price for s in eligible_slots))
        
        # Take top X unique price levels
        selected_prices = set(unique_prices[:self._top_x_count])
        
        # Get ALL slots at those price levels
        slots_at_selected_prices = [s for s in eligible_slots if s.price in selected_prices]
        
        # Sort by price then time and assign ranks (same price = same rank)
        sorted_by_price = sorted(slots_at_selected_prices, key=lambda s: (s.price, s.start))
        
        # Assign ranks based on unique price levels (all slots at same price get same rank)
        price_to_rank = {p: rank for rank, p in enumerate(unique_prices[:self._top_x_count], start=1)}
        
        cheapest = []
        for slot in sorted_by_price:
            cheapest.append(PriceSlot(
                start=slot.start,
                end=slot.end,
                price=slot.price,
                rank=price_to_rank[slot.price],
            ))
        
        # Sort cheapest by time for display
        cheapest_by_time = sorted(cheapest, key=lambda s: s.start)
        
        # Calculate stats from all day slots (not just eligible)
        all_prices = [s.price for s in day_slots]
        min_price = min(all_prices)
        max_price = max(all_prices)
        avg_price = sum(all_prices) / len(all_prices)
        
        analysis = DailyPriceAnalysis(
            target_date=target_date,
            all_slots=sorted(day_slots, key=lambda s: s.start),
            cheapest_slots=cheapest_by_time,
            min_price=min_price,
            max_price=max_price,
            avg_price=avg_price,
            price_threshold=self._price_threshold,
            slots_filtered_by_threshold=slots_filtered_count,
        )
        
        self._log_analysis(analysis)
        return analysis
    
    def _parse_slots_for_date(self, price_curve: List[Dict], target_date: date) -> List[PriceSlot]:
        """Parse price curve and filter for a specific date."""
        slots = []
        
        for entry in price_curve:
            try:
                start = self._parse_timestamp(entry.get("start"))
                end = self._parse_timestamp(entry.get("end"))
                price = float(entry.get("price", 0))
                
                # Filter for target date
                if start.date() == target_date:
                    slots.append(PriceSlot(
                        start=start,
                        end=end,
                        price=price,
                        rank=0,  # Will be assigned later
                    ))
            except (TypeError, ValueError) as exc:
                logger.debug("Skipping malformed price entry %s: %s", entry, exc)
                continue
        
        return slots
    
    def _parse_timestamp(self, value: Optional[str]) -> datetime:
        """Parse an ISO timestamp string to a timezone-aware datetime."""
        if not value:
            raise ValueError("Missing timestamp")
        
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=self._tz)
        return dt.astimezone(self._tz)
    
    def _log_analysis(self, analysis: DailyPriceAnalysis) -> None:
        """Log the analysis results (debug level)."""
        # Count unique price levels in selected slots
        unique_prices_selected = len(set(s.price for s in analysis.cheapest_slots))
        
        threshold_info = ""
        if analysis.price_threshold is not None:
            threshold_info = f", threshold={analysis.price_threshold:.2f} EUR/kWh"
            if analysis.slots_filtered_by_threshold > 0:
                threshold_info += f" (filtered {analysis.slots_filtered_by_threshold} slots)"
        
        logger.debug(
            "📊 Price Analysis for %s: %d slots, min=%.2f, max=%.2f, avg=%.2f EUR/kWh%s",
            analysis.target_date.isoformat(),
            len(analysis.all_slots),
            analysis.min_price,
            analysis.max_price,
            analysis.avg_price,
            threshold_info,
        )
        
        if not analysis.cheapest_slots:
            logger.debug("   ⚠️ No slots selected (all above threshold)")
            return
        
        logger.debug(
            "⚡ Selected %d slots across %d unique price levels:",
            len(analysis.cheapest_slots),
            unique_prices_selected,
        )
        
        for slot in analysis.cheapest_slots:
            logger.debug(
                "   Rank %2d: %s - %s @ %.2f EUR/kWh",
                slot.rank,
                slot.start.strftime("%H:%M"),
                slot.end.strftime("%H:%M"),
                slot.price,
            )
