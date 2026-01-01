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


def calculate_export_price(market_price: float, vat_multiplier: float, markup: float, energy_tax: float,
                         fixed_bonus: float, bonus_pct: float, is_daylight_active: bool) -> float:
    """Calculate export price (Zonneplan 2026).
    
    Rules:
    - Base: market_price + markup + energy_tax + fixed_bonus
    - Solar Bonus (+10%): Only during daylight AND positive market price
    - Night: No bonus
    - Negative price: No bonus, price = market_price + markup + energy_tax (netting applies)
    - All calculated including VAT (netting)
    
    Args:
        market_price: Market price in EUR/kWh
        vat_multiplier: VAT multiplier (e.g., 1.21)
        markup: Fixed markup in EUR/kWh
        energy_tax: Energy tax in EUR/kWh
        fixed_bonus: Fixed bonus in EUR/kWh
        bonus_pct: Bonus percentage (e.g., 0.10 for 10%)
        is_daylight_active: Whether it is currently daylight
        
    Returns:
        Final price in EUR/kWh rounded to 4 decimals
    """
    # Base price includes markup and tax (netting)
    # Note: For negative prices, Zonneplan might have specific rules, but assuming full netting
    # implies you get back what you would have paid (including tax/markup).
    base_price = market_price + markup + energy_tax + fixed_bonus
    
    # Apply solar bonus if daylight and price is positive
    # Bonus is applied to the base price (including tax/markup) or just spot?
    # Assuming bonus applies to the total value for now to ensure Export > Import.
    if is_daylight_active and market_price > 0:
        base_price = base_price * (1 + bonus_pct)
            
    # Apply VAT (netting)
    result = base_price * vat_multiplier
    return round(result, 4)
