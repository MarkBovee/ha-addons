"""Price analyzer for Water Heater Scheduler add-on.

Reads price data from energy-prices add-on sensor and provides
methods to find optimal heating times.
"""

import logging
from datetime import datetime, time, timedelta
from typing import Dict, Optional, Tuple, Any
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)


class PriceAnalyzer:
    """Analyze electricity prices to find optimal heating times."""
    
    def __init__(self, timezone: str = "Europe/Amsterdam"):
        """Initialize the price analyzer.
        
        Args:
            timezone: Timezone for price calculations
        """
        self.timezone = ZoneInfo(timezone)
        self._price_curve: Dict[datetime, float] = {}
        self._current_price: Optional[float] = None
    
    def update_prices(self, sensor_state: Dict[str, Any]) -> bool:
        """Update price data from sensor state.
        
        Args:
            sensor_state: Home Assistant sensor state dict with attributes
            
        Returns:
            True if prices were successfully updated
        """
        try:
            # Get current price from state
            self._current_price = float(sensor_state.get("state", 0))
            
            # Get price curve from attributes
            attributes = sensor_state.get("attributes", {})
            price_curve_raw = attributes.get("price_curve")
            
            if not price_curve_raw:
                logger.warning("No price_curve in sensor attributes")
                return False

            # Parse price curve into datetime keys (support dict or list structures)
            self._price_curve = {}
            if isinstance(price_curve_raw, dict):
                source_iterable = price_curve_raw.items()
            else:
                # Expect list of entries with `start` and `price`
                source_iterable = []
                for entry in price_curve_raw:
                    if not isinstance(entry, dict):
                        logger.debug("Skipping price entry with unexpected type: %s", type(entry))
                        continue
                    start = entry.get("start") or entry.get("time")
                    price = entry.get("price")
                    if start is None or price is None:
                        logger.debug("Skipping price entry missing start/price: %s", entry)
                        continue
                    source_iterable.append((start, price))
            
            for time_str, price in source_iterable:
                try:
                    dt = datetime.fromisoformat(str(time_str))
                    self._price_curve[dt] = float(price)
                except (ValueError, TypeError) as e:
                    logger.debug("Failed to parse price entry %s: %s", time_str, e)
            
            logger.debug("Updated prices: %d intervals, current=%.4f", 
                        len(self._price_curve), self._current_price or 0)
            return len(self._price_curve) > 0
            
        except Exception as e:
            logger.error("Failed to update prices: %s", e)
            return False
    
    @property
    def current_price(self) -> Optional[float]:
        """Get current electricity price."""
        return self._current_price
    
    @property
    def has_prices(self) -> bool:
        """Check if price data is available."""
        return len(self._price_curve) > 0
    
    def is_negative_price(self) -> bool:
        """Check if current price is negative or zero (free energy)."""
        return self._current_price is not None and self._current_price <= 0
    
    def get_prices_in_window(
        self, 
        start_time: time, 
        end_time: time, 
        target_date: Optional[datetime] = None
    ) -> Dict[datetime, float]:
        """Get prices within a time window.
        
        Args:
            start_time: Start of window (time only)
            end_time: End of window (time only)
            target_date: Date to use (default: today)
            
        Returns:
            Dict mapping datetime to price for intervals in window
        """
        now = datetime.now(self.timezone)
        if target_date is None:
            target_date = now
        
        # Build window boundaries for the target date
        window_start = datetime.combine(target_date.date(), start_time, tzinfo=self.timezone)
        
        # Handle overnight windows (e.g., 22:00-06:00)
        if end_time <= start_time:
            window_end = datetime.combine(target_date.date() + timedelta(days=1), end_time, tzinfo=self.timezone)
        else:
            window_end = datetime.combine(target_date.date(), end_time, tzinfo=self.timezone)
        
        # Filter prices within window
        result = {}
        for dt, price in self._price_curve.items():
            if window_start <= dt < window_end:
                result[dt] = price
        
        return result
    
    def get_lowest_price_in_window(
        self, 
        start_time: time, 
        end_time: time,
        target_date: Optional[datetime] = None
    ) -> Optional[Tuple[datetime, float]]:
        """Find the lowest price interval in a time window.
        
        Args:
            start_time: Start of window
            end_time: End of window
            target_date: Date to use (default: today)
            
        Returns:
            Tuple of (datetime, price) for lowest price, or None if no prices
        """
        prices = self.get_prices_in_window(start_time, end_time, target_date)
        if not prices:
            return None
        
        lowest_dt = min(prices, key=prices.get)
        return (lowest_dt, prices[lowest_dt])
    
    def get_lowest_night_price(
        self,
        night_start: time,
        night_end: time,
        target_date: Optional[datetime] = None,
    ) -> Optional[Tuple[datetime, float]]:
        """Get the lowest price in the night window.
        
        Args:
            night_start: Night window start (e.g., 00:00)
            night_end: Night window end (e.g., 06:00)
            
        Returns:
            Tuple of (datetime, price) or None
        """
        return self.get_lowest_price_in_window(night_start, night_end, target_date)
    
    def get_lowest_day_price(
        self,
        day_start: time,
        day_end: time = time(23, 45),
        target_date: Optional[datetime] = None,
    ) -> Optional[Tuple[datetime, float]]:
        """Get the lowest price in the day window.
        
        Args:
            day_start: Day window start (typically after night window)
            day_end: Day window end (default: 23:45)
            
        Returns:
            Tuple of (datetime, price) or None
        """
        return self.get_lowest_price_in_window(day_start, day_end, target_date)
    
    def compare_night_vs_day(
        self,
        night_start: time,
        night_end: time,
        target_date: Optional[datetime] = None,
    ) -> Optional[bool]:
        """Compare if night prices are cheaper than day prices.
        
        Args:
            night_start: Night window start
            night_end: Night window end
            
        Returns:
            True if night is cheaper, False if day is cheaper, None if no data
        """
        night_lowest = self.get_lowest_night_price(night_start, night_end, target_date)
        day_lowest = self.get_lowest_day_price(night_end, target_date=target_date)
        
        if night_lowest is None or day_lowest is None:
            return None
        
        return night_lowest[1] < day_lowest[1]
    
    def get_tomorrow_prices(self) -> Dict[datetime, float]:
        """Get prices for tomorrow if available.
        
        Returns:
            Dict of tomorrow's prices, empty if not available
        """
        now = datetime.now(self.timezone)
        tomorrow = now.date() + timedelta(days=1)
        
        result = {}
        for dt, price in self._price_curve.items():
            if dt.date() == tomorrow:
                result[dt] = price
        
        return result
    
    def has_tomorrow_prices(self) -> bool:
        """Check if tomorrow's prices are available."""
        return len(self.get_tomorrow_prices()) > 0
    
    def get_tomorrow_night_avg(
        self,
        night_end: time = time(6, 0),
    ) -> Optional[float]:
        """Get average price for tomorrow's night window (00:00 to night_end).

        This matches the NetDaemon WaterHeater.cs logic which uses GetNextNightPrice
        to get tomorrow's early morning prices for comparison.

        Args:
            night_end: End of night window (default 06:00)

        Returns:
            Average price for tomorrow 00:00-night_end, or None if no data
        """
        now = datetime.now(self.timezone)
        tomorrow = now.date() + timedelta(days=1)
        tomorrow_ref = datetime.combine(tomorrow, time(0, 0), tzinfo=self.timezone)

        tomorrow_night_prices = self.get_prices_in_window(
            time(0, 0),
            night_end,
            target_date=tomorrow_ref,
        )

        if not tomorrow_night_prices:
            return None

        return sum(tomorrow_night_prices.values()) / len(tomorrow_night_prices)

    def compare_today_vs_tomorrow(
        self,
        evening_start: time = time(18, 0),
        night_end: time = time(6, 0),
    ) -> Optional[bool]:
        """Compare today's evening prices vs tomorrow night's prices.

        Compares only the evening window (default 18:00-00:00) against
        the following night's window (default 00:00-06:00). This avoids
        averaging a full 24h horizon that can mute near-term spikes/dips.

        Args:
            evening_start: Start of today's comparison window (inclusive)
            night_end: End of tomorrow's night window (exclusive)
            
        Returns:
            True if today's evening is cheaper, False if tomorrow night is cheaper,
            None if data is missing
        """
        now = datetime.now(self.timezone)
        today = now.date()
        tomorrow = today + timedelta(days=1)

        today_ref = datetime.combine(today, evening_start, tzinfo=self.timezone)
        tomorrow_ref = datetime.combine(tomorrow, time(0, 0), tzinfo=self.timezone)

        evening_prices = self.get_prices_in_window(
            evening_start,
            time(23, 59, 59),
            target_date=today_ref,
        )
        tomorrow_night_prices = self.get_prices_in_window(
            time(0, 0),
            night_end,
            target_date=tomorrow_ref,
        )

        if not evening_prices or not tomorrow_night_prices:
            return None

        evening_avg = sum(evening_prices.values()) / len(evening_prices)
        tomorrow_avg = sum(tomorrow_night_prices.values()) / len(tomorrow_night_prices)

        return evening_avg < tomorrow_avg
    
    def get_optimal_legionella_start(
        self, 
        day_start: time, 
        duration_hours: int
    ) -> Optional[datetime]:
        """Find optimal start time for legionella cycle.
        
        Checks if 15 minutes before is cheaper than 15 minutes after
        the lowest price slot, and adjusts accordingly.
        
        Args:
            day_start: Start of day window
            duration_hours: Duration of legionella cycle
            
        Returns:
            Optimal start datetime, or None if no prices
        """
        lowest = self.get_lowest_day_price(day_start)
        if lowest is None:
            return None
        
        start_time = lowest[0]
        
        # Check if shifting 15 minutes earlier is better
        prev_time = start_time - timedelta(minutes=15)
        next_time = start_time + timedelta(minutes=15)
        
        prev_price = self._price_curve.get(prev_time)
        next_price = self._price_curve.get(next_time)
        
        if prev_price is not None and next_price is not None:
            if prev_price < next_price:
                logger.debug("Legionella: Shifted start 15min earlier (prev=%.4f < next=%.4f)",
                            prev_price, next_price)
                return prev_time
        
        return start_time
