"""Data models for energy prices."""

from dataclasses import dataclass
from datetime import datetime


@dataclass
class PriceInterval:
    """Represents a single price interval (15 minutes)."""
    
    start: datetime
    end: datetime
    price_eur_mwh: float
    
    def price_cents_kwh(self) -> float:
        """Convert price from EUR/MWh to cents/kWh.
        
        Returns:
            Price in cents/kWh (EUR/MWh × 0.1)
        """
        return round(self.price_eur_mwh * 0.1, 4)
    
    @classmethod
    def from_dict(cls, data: dict) -> "PriceInterval":
        """Create PriceInterval from API response dict.
        
        Args:
            data: Dictionary from Nord Pool API
            
        Returns:
            PriceInterval instance
        """
        # Placeholder - will be implemented in Phase 2
        raise NotImplementedError("from_dict() not yet implemented")
    
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
