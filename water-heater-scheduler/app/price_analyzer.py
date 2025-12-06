"""Price analysis functions for Water Heater Scheduler.

Handles parsing price curves from sensors and finding optimal heating windows.
"""

from datetime import datetime, timedelta
from typing import Dict, Tuple, Any


def parse_price_curve(sensor_state: Dict[str, Any]) -> Dict[datetime, float]:
    """Parse price_curve from sensor attributes into datetime->price dict.
    
    Mirrors PriceHelper.PricesToday in NetDaemon.
    """
    prices = {}
    attributes = sensor_state.get("attributes", {})
    price_curve = attributes.get("price_curve", [])
    
    for entry in price_curve:
        if not isinstance(entry, dict):
            continue
        start_str = entry.get("start") or entry.get("time")
        price = entry.get("price")
        if start_str is None or price is None:
            continue
        try:
            dt = datetime.fromisoformat(str(start_str))
            # Convert to local time for comparison (strip timezone for simple comparisons)
            if dt.tzinfo is not None:
                dt = dt.replace(tzinfo=None)
            prices[dt] = float(price)
        except (ValueError, TypeError):
            continue
    
    return prices


def get_lowest_price_in_range(prices: Dict[datetime, float], start_hour: int, end_hour: int, 
                               target_date: datetime) -> Tuple[datetime, float]:
    """Get the lowest price in a time range.
    
    Mirrors PriceHelper.GetLowestNightPrice / GetLowestDayPrice.
    """
    target_day = target_date.date()
    filtered = {}
    
    for dt, price in prices.items():
        if dt.date() != target_day:
            continue
        hour = dt.hour
        if start_hour <= end_hour:
            # Normal range (e.g., 6-23)
            if start_hour <= hour < end_hour:
                filtered[dt] = price
        else:
            # Overnight range (e.g., 0-6)
            if hour >= start_hour or hour < end_hour:
                filtered[dt] = price
    
    if not filtered:
        # Return a default if no prices found
        default_time = target_date.replace(hour=start_hour, minute=0, second=0, microsecond=0)
        return (default_time, 0.5)
    
    lowest_dt = min(filtered, key=filtered.get)
    return (lowest_dt, filtered[lowest_dt])


def get_lowest_night_price(prices: Dict[datetime, float], target_date: datetime) -> Tuple[datetime, float]:
    """Get lowest price during night hours (0:00 - 6:00)."""
    return get_lowest_price_in_range(prices, 0, 6, target_date)


def get_lowest_day_price(prices: Dict[datetime, float], target_date: datetime) -> Tuple[datetime, float]:
    """Get lowest price during day hours (6:00 - 24:00)."""
    return get_lowest_price_in_range(prices, 6, 24, target_date)


def get_next_night_price(prices_tomorrow: Dict[datetime, float], tomorrow: datetime) -> Tuple[datetime, float]:
    """Get lowest night price for tomorrow."""
    return get_lowest_night_price(prices_tomorrow, tomorrow)


def get_price_level(current_price: float, prices: Dict[datetime, float]) -> str:
    """Determine price level (None/Low/Medium/High) based on fixed price thresholds.
    
    Matches NetDaemon PriceHelper.GetEnergyPriceLevel() exactly:
    - None: price < 0 (actual negative/free energy)
    - Low: price < 0.10 EUR/kWh
    - Medium: price < 0.35 EUR/kWh (and below threshold)
    - High: price < 0.45 EUR/kWh or above threshold
    - Maximum: price >= 0.45 EUR/kWh
    """
    if not prices:
        return "Medium"
    
    # Calculate price threshold (average of today's prices, min 0.28)
    avg_price = sum(prices.values()) / len(prices) if prices else 0.28
    price_threshold = max(avg_price, 0.28)
    
    # Fixed thresholds matching NetDaemon PriceHelper.cs GetEnergyPriceLevel()
    if current_price < 0:
        return "None"  # Actual negative price - free energy
    elif current_price < 0.10:
        return "Low"   # Very cheap (< 10 cents/kWh)
    elif current_price < 0.35:
        # Medium if below threshold, High if above
        return "Medium" if current_price < price_threshold else "High"
    elif current_price < 0.45:
        return "High"
    else:
        return "Maximum"
