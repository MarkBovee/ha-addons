"""Energy Prices add-on main entry point."""

import logging
import signal
import time
import json
import os
import requests
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional
from zoneinfo import ZoneInfo

from .nordpool_api import NordPoolApi
from .models import PriceInterval
from .price_calculator import TemplateProcessor, PriceCalculator

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Shutdown flag for graceful termination
shutdown_flag = False


def signal_handler(signum, frame):
    """Handle SIGTERM and SIGINT for graceful shutdown."""
    global shutdown_flag
    logger.info("Received signal %d, initiating graceful shutdown...", signum)
    shutdown_flag = True
def load_config() -> dict:
    """Load configuration from /data/options.json (HA Supervisor pattern).
    
    Returns:
        Configuration dictionary
        
    Raises:
        FileNotFoundError: If config file doesn't exist
        json.JSONDecodeError: If config is invalid JSON
        KeyError: If required fields are missing
    """
    config_path = '/data/options.json'
    
    # For local development, allow override via environment
    if not os.path.exists(config_path):
        logger.warning("Config file %s not found, using environment variables", config_path)
        return {
            'delivery_area': os.getenv('DELIVERY_AREA', 'NL'),
            'currency': os.getenv('CURRENCY', 'EUR'),
            'timezone': os.getenv('TIMEZONE', 'CET'),
            'import_price_template': os.getenv('IMPORT_PRICE_TEMPLATE', '{{ marktprijs | round(4) }}'),
            'export_price_template': os.getenv('EXPORT_PRICE_TEMPLATE', '{{ marktprijs | round(4) }}'),
            'fetch_interval_minutes': int(os.getenv('FETCH_INTERVAL_MINUTES', '60'))
        }
    
    with open(config_path, 'r') as f:
        config = json.load(f)
    
    # Validate required fields
    required = ['delivery_area', 'currency', 'timezone', 'import_price_template', 
                'export_price_template', 'fetch_interval_minutes']
    for field in required:
        if field not in config:
            raise KeyError(f"Required config field missing: {field}")
    
    logger.info("Loaded configuration: area=%s, currency=%s, timezone=%s, interval=%dm",
               config['delivery_area'], config['currency'], config['timezone'], 
               config['fetch_interval_minutes'])
    
    return config


def get_ha_api_token() -> str:
    """Get Home Assistant Supervisor API token.
    
    Returns:
        Supervisor token for authentication
    """
    return os.getenv('SUPERVISOR_TOKEN', '')


def create_or_update_entity(entity_id: str, state: str, attributes: dict, token: str):
    """Create or update a Home Assistant entity.
    
    Args:
        entity_id: Entity ID (e.g., sensor.ep_price_import)
        state: Entity state value
        attributes: Entity attributes dictionary
        token: Supervisor API token
        
    Raises:
        requests.HTTPError: If API request fails
    """
    url = f"http://supervisor/core/api/states/{entity_id}"
    headers = {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json'
    }
    payload = {
        'state': state,
        'attributes': attributes
    }
    
    response = requests.post(url, json=payload, headers=headers, timeout=10)
    response.raise_for_status()
    logger.debug("Updated entity %s: state=%s", entity_id, state)


def fetch_and_process_prices(nordpool: NordPoolApi, config: dict, 
                            import_processor: TemplateProcessor,
                            export_processor: TemplateProcessor) -> Optional[dict]:
    """Fetch prices, apply templates, calculate percentiles.
    
    Args:
        nordpool: Nord Pool API client
        config: Configuration dictionary
        import_processor: Template processor for import prices
        export_processor: Template processor for export prices
        
    Returns:
        Dictionary with processed prices, percentiles, current_level
        None if fetch/processing fails
    """
    try:
        # Get today and tomorrow in configured timezone
        tz = ZoneInfo(config['timezone'])
        now = datetime.now(tz)
        today = now.date()
        tomorrow = today + timedelta(days=1)
        
        # Fetch prices for both days
        logger.info("Fetching prices for %s and %s", today, tomorrow)
        today_intervals = nordpool.fetch_prices(today, config['delivery_area'], config['currency'])
        tomorrow_intervals = nordpool.fetch_prices(tomorrow, config['delivery_area'], config['currency'])
        
        # Combine intervals
        all_intervals = today_intervals + tomorrow_intervals
        if not all_intervals:
            logger.warning("No price data available")
            return None
        
        logger.info("Fetched %d intervals total (%d today, %d tomorrow)", 
                   len(all_intervals), len(today_intervals), len(tomorrow_intervals))
        
        # Apply templates to calculate final prices
        import_prices = []
        export_prices = []
        price_curve_import = []
        price_curve_export = []
        
        for interval in all_intervals:
            market_price = interval.price_cents_kwh()
            
            try:
                import_price = import_processor.calculate_price(market_price)
                export_price = export_processor.calculate_price(market_price)
                
                import_prices.append(import_price)
                export_prices.append(export_price)
                
                price_curve_import.append({
                    'start': interval.start.isoformat(),
                    'end': interval.end.isoformat(),
                    'price': import_price
                })
                price_curve_export.append({
                    'start': interval.start.isoformat(),
                    'end': interval.end.isoformat(),
                    'price': export_price
                })
            except Exception as e:
                logger.warning("Failed to calculate price for interval %s: %s", 
                             interval.start.isoformat(), e)
                continue
        
        if not import_prices:
            logger.error("No prices calculated successfully")
            return None
        
        # Calculate percentiles from import prices
        percentiles = PriceCalculator.calculate_percentiles(import_prices)
        logger.info("Percentiles: P20=%.4f, P40=%.4f, P60=%.4f", 
                   percentiles['p20'], percentiles['p40'], percentiles['p60'])
        
        # Find current interval and classify price level
        now_utc = datetime.now(ZoneInfo('UTC'))
        current_import = None
        current_export = None
        
        for i, interval in enumerate(all_intervals):
            if interval.start <= now_utc < interval.end:
                if i < len(import_prices):
                    current_import = import_prices[i]
                    current_export = export_prices[i]
                break
        
        if current_import is None:
            logger.warning("No current price found for %s", now_utc.isoformat())
            current_import = import_prices[0]  # Fallback to first price
            current_export = export_prices[0]
        
        price_level = PriceCalculator.classify_price(
            current_import, percentiles['p20'], percentiles['p40'], percentiles['p60']
        )
        
        logger.info("Current import price: %.4f cents/kWh, level: %s", 
                   current_import, price_level)
        
        return {
            'current_import': current_import,
            'current_export': current_export,
            'price_curve_import': price_curve_import,
            'price_curve_export': price_curve_export,
            'percentiles': percentiles,
            'price_level': price_level,
            'last_update': datetime.now(ZoneInfo('UTC')).isoformat()
        }
        
    except Exception as e:
        logger.error("Failed to fetch/process prices: %s", e, exc_info=True)
        return None


def update_ha_entities(data: dict, token: str):
    """Update Home Assistant entities with price data.
    
    Args:
        data: Processed price data dictionary
        token: Supervisor API token
    """
    try:
        # Update sensor.ep_price_import
        create_or_update_entity(
            'sensor.ep_price_import',
            str(data['current_import']),
            {
                'unit_of_measurement': 'cents/kWh',
                'device_class': 'monetary',
                'friendly_name': 'Electricity Import Price',
                'price_curve': data['price_curve_import'],
                'percentiles': data['percentiles'],
                'last_update': data['last_update']
            },
            token
        )
        
        # Update sensor.ep_price_export
        create_or_update_entity(
            'sensor.ep_price_export',
            str(data['current_export']),
            {
                'unit_of_measurement': 'cents/kWh',
                'device_class': 'monetary',
                'friendly_name': 'Electricity Export Price',
                'price_curve': data['price_curve_export'],
                'last_update': data['last_update']
            },
            token
        )
        
        # Update sensor.ep_price_level
        create_or_update_entity(
            'sensor.ep_price_level',
            data['price_level'],
            {
                'friendly_name': 'Electricity Price Level',
                'current_price': data['current_import'],
                'p20': data['percentiles']['p20'],
                'p40': data['percentiles']['p40'],
                'p60': data['percentiles']['p60'],
                'classification_rules': 'None: <P20, Low: P20-P40, Medium: P40-P60, High: >=P60'
            },
            token
        )
        
        logger.info("Successfully updated all HA entities")
        
    except Exception as e:
        logger.error("Failed to update HA entities: %s", e, exc_info=True)




def main():
    """Main entry point for the add-on."""
    logger.info("Energy Prices add-on starting...")
    
    # Register signal handlers
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    
    try:
        # Load configuration
        config = load_config()
        
        # Initialize API client
        nordpool = NordPoolApi()
        
        # Initialize template processors (fail-fast validation)
        logger.info("Validating templates...")
        import_processor = TemplateProcessor(config['import_price_template'])
        export_processor = TemplateProcessor(config['export_price_template'])
        logger.info("Templates validated successfully")
        
        # Get HA API token
        ha_token = get_ha_api_token()
        if not ha_token:
            logger.warning("SUPERVISOR_TOKEN not set, entity updates will fail")
        
        fetch_interval = config['fetch_interval_minutes'] * 60
        logger.info("Starting main loop (fetch interval: %d minutes)", 
                   config['fetch_interval_minutes'])
        
        # Main loop
        while not shutdown_flag:
            try:
                # Fetch and process prices
                data = fetch_and_process_prices(nordpool, config, import_processor, export_processor)
                
                if data:
                    # Update HA entities
                    update_ha_entities(data, ha_token)
                else:
                    logger.warning("No price data to update entities")
                
            except Exception as e:
                logger.error("Error in main loop iteration: %s", e, exc_info=True)
            
            # Sleep with shutdown check every second
            for _ in range(fetch_interval):
                if shutdown_flag:
                    break
                time.sleep(1)
        
    except Exception as e:
        logger.error("Fatal error in main: %s", e, exc_info=True)
        return 1
    
    logger.info("Energy Prices add-on stopped")
    return 0


if __name__ == "__main__":
    exit(main())
