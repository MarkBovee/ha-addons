"""Data models for energy prices."""

from dataclasses import dataclass
from datetime import datetime


@dataclass
class PriceInterval:
    """Represents a single price interval (15 minutes)."""
    
    start: datetime
    end: datetime
    price_eur_mwh: float
    
    def price_eur_kwh(self) -> float:
        """Convert price from EUR/MWh to EUR/kWh.
        
        Returns:
            Price in EUR/kWh (EUR/MWh / 1000), rounded to 4 decimals
        """
        return round(self.price_eur_mwh / 1000, 4)
    
    def price_cents_kwh(self) -> float:
        """Convert price from EUR/MWh to cents/kWh.
        
        Returns:
            Price in cents/kWh (EUR/MWh × 0.1), rounded to 4 decimals
        """
        return round(self.price_eur_mwh * 0.1, 4)
    
    @classmethod
    def from_dict(cls, data: dict) -> "PriceInterval":
        """Create PriceInterval from API response dict.
        
        Args:
            data: Dictionary from Nord Pool API multiAreaEntries
            
        Returns:
            PriceInterval instance with UTC-aware timestamps
            
        Raises:
            KeyError: If required fields are missing
            ValueError: If timestamp parsing fails
            
        Example API response entry:
        {
            "deliveryStart": "2025-11-25T00:00:00Z",
            "deliveryEnd": "2025-11-25T00:15:00Z",
            "entryPerArea": {
                "NL": 45.67
            }
        }
        """
        # Parse ISO 8601 timestamps (already UTC with Z suffix)
        start_str = data['deliveryStart']
        end_str = data['deliveryEnd']
        
        # Python 3.11+ handles Z suffix, but for compatibility use replace
        start = datetime.fromisoformat(start_str.replace('Z', '+00:00'))
        end = datetime.fromisoformat(end_str.replace('Z', '+00:00'))
        
        # Extract price from entryPerArea (nested dict keyed by delivery area)
        # We assume single area per request, take first value
        entry_per_area = data['entryPerArea']
        if not entry_per_area:
            raise ValueError("entryPerArea is empty")
        
        # Get first (and should be only) area's price
        price_eur_mwh = next(iter(entry_per_area.values()))
        
        return cls(
            start=start,
            end=end,
            price_eur_mwh=float(price_eur_mwh)
        )
    
    def to_dict(self) -> dict:
        """Convert PriceInterval to dict for HA entity attributes.
        
        Returns:
            Dictionary with start, end, and price
        """
        return {
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "price": self.price_cents_kwh()
        }
