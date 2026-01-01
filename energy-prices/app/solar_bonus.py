"""Solar bonus calculations for Zonneplan 2026 pricing."""

import logging
from datetime import datetime
from astral import LocationInfo
from astral.sun import sun

logger = logging.getLogger(__name__)


def is_daylight(timestamp: datetime, latitude: float, longitude: float) -> bool:
    """Check if timestamp is between sunrise and sunset at location.
    
    Args:
        timestamp: Datetime to check
        latitude: Location latitude
        longitude: Location longitude
        
    Returns:
        True if between sunrise and sunset, False otherwise
    """
    try:
        # Create location info (name/region/timezone not strictly needed for coords)
        city = LocationInfo("", "", "", latitude, longitude)
        
        # Calculate sun times for the specific date
        # Ensure we use the same timezone as the timestamp
        s = sun(city.observer, date=timestamp.date(), tzinfo=timestamp.tzinfo)
        
        return s['sunrise'] <= timestamp < s['sunset']
    except Exception as e:
        logger.warning("Failed to calculate daylight for %s: %s", timestamp, e)
        # Fallback: 06:00 to 22:00 roughly covers daylight
        return 6 <= timestamp.hour < 22


def get_sun_times(date_obj, latitude: float, longitude: float):
    """Get sunrise and sunset times for a specific date and location.
    
    Args:
        date_obj: Date to check
        latitude: Location latitude
        longitude: Location longitude
        
    Returns:
        Tuple of (sunrise, sunset) datetimes, or (None, None) on error
    """
    try:
        city = LocationInfo("", "", "", latitude, longitude)
        s = sun(city.observer, date=date_obj)
        return s['sunrise'], s['sunset']
    except Exception as e:
        logger.warning("Failed to calculate sun times for %s: %s", date_obj, e)
        return None, None


def calculate_export_price(market_price: float, vat_multiplier: float, fixed_bonus: float, 
                         bonus_pct: float, is_daylight_active: bool) -> float:
    """Calculate export price (Zonneplan 2026).
    
    Rules:
    - Base: market_price + fixed_bonus
    - Solar Bonus (+10%): Only during daylight AND positive market price
    - Night: No bonus
    - Negative price: No bonus, price = market_price
    - All calculated including VAT (netting)
    
    Args:
        market_price: Market price in EUR/kWh
        vat_multiplier: VAT multiplier (e.g., 1.21)
        fixed_bonus: Fixed bonus in EUR/kWh
        bonus_pct: Bonus percentage (e.g., 0.10 for 10%)
        is_daylight_active: Whether it is currently daylight
        
    Returns:
        Final price in EUR/kWh rounded to 4 decimals
    """
    # Negative prices: no bonus, just the market price
    if market_price < 0:
        base_price = market_price
    else:
        # Positive prices: market + fixed bonus
        base_price = market_price + fixed_bonus
        
        # Apply solar bonus if daylight and price is positive
        if is_daylight_active:
            base_price = base_price * (1 + bonus_pct)
            
    # Apply VAT (netting)
    result = base_price * vat_multiplier
    return round(result, 4)
