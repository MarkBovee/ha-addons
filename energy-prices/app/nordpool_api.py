"""Nord Pool API client for fetching day-ahead electricity prices."""

import logging
from typing import List
from datetime import date
import requests

from .models import PriceInterval

logger = logging.getLogger(__name__)


class NordPoolApi:
    """Client for Nord Pool Day-Ahead Prices API."""
    
    def __init__(self):
        """Initialize Nord Pool API client with session for connection pooling."""
        self.base_url = "https://dataportal-api.nordpoolgroup.com/api/DayAheadPrices"
        self.session = requests.Session()
        # CORS headers required by Nord Pool API
        self.session.headers.update({
            'Origin': 'https://data.nordpoolgroup.com',
            'Referer': 'https://data.nordpoolgroup.com/'
        })
        logger.info("Initialized Nord Pool API client with session")
    
    def fetch_prices(self, target_date: date, delivery_area: str, currency: str) -> List[PriceInterval]:
        """Fetch prices for a specific date and delivery area.
        
        Args:
            target_date: Date to fetch prices for
            delivery_area: Delivery area code (e.g., "NL")
            currency: Currency code (e.g., "EUR")
            
        Returns:
            List of PriceInterval objects (sorted by start_time)
            Empty list if data not available (HTTP 204)
            
        Raises:
            requests.HTTPError: If API returns error status (4xx/5xx)
            ValueError: If response format is invalid
        """
        date_str = target_date.strftime("%Y-%m-%d")
        params = {
            'date': date_str,
            'market': 'DayAhead',
            'deliveryArea': delivery_area,
            'currency': currency
        }
        
        logger.info("Fetching prices for %s, area=%s, currency=%s", date_str, delivery_area, currency)
        
        try:
            response = self.session.get(self.base_url, params=params, timeout=30)
            
            # HTTP 204 means data not yet available (typically tomorrow's prices before 13:00)
            if response.status_code == 204:
                logger.info("Prices not yet available for %s (HTTP 204)", date_str)
                return []
            
            # Raise exception for error status codes
            response.raise_for_status()
            
            # Parse JSON response
            data = response.json()
            
            # Extract multiAreaEntries (contains price data)
            if 'multiAreaEntries' not in data:
                logger.error("Response missing 'multiAreaEntries' field")
                raise ValueError("Invalid API response format: missing 'multiAreaEntries'")
            
            entries = data['multiAreaEntries']
            if not entries:
                logger.warning("No price entries found for %s", date_str)
                return []
            
            # Convert to PriceInterval objects
            intervals = []
            for entry in entries:
                try:
                    interval = PriceInterval.from_dict(entry)
                    intervals.append(interval)
                except (KeyError, ValueError) as e:
                    logger.warning("Skipping invalid entry: %s", e)
                    continue
            
            # Sort by start time
            intervals.sort(key=lambda x: x.start)
            
            logger.info("Fetched %d price intervals for %s", len(intervals), date_str)
            if intervals:
                # Log first interval as example
                first = intervals[0]
                logger.debug("First interval: %s → EUR/MWh: %.4f, cents/kWh: %.4f",
                           first.start.isoformat(), first.price_eur_mwh, first.price_cents_kwh())
            
            return intervals
            
        except requests.Timeout:
            logger.error("Request timed out after 30s")
            raise
        except requests.RequestException as e:
            logger.error("API request failed: %s", e)
            raise
