"""Energy Prices add-on main entry point."""

import logging
import time
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from zoneinfo import ZoneInfo

from .nordpool_api import NordPoolApi
from .models import PriceInterval
from .price_calculator import PriceCalculator

# Import shared modules
from shared.addon_base import setup_logging, setup_signal_handlers, sleep_with_shutdown_check
from shared.ha_api import HomeAssistantApi, get_ha_api_config
from shared.config_loader import load_addon_config, get_run_once_mode
from shared.mqtt_setup import setup_mqtt_client, is_mqtt_available

# Try to import MQTT Discovery for entity publishing
try:
    from shared.ha_mqtt_discovery import EntityConfig
    MQTT_ENTITY_CONFIG_AVAILABLE = True
except ImportError:
    MQTT_ENTITY_CONFIG_AVAILABLE = False

# Configure logging
logger = setup_logging(name=__name__)


# Energy Prices specific configuration defaults
EP_CONFIG_DEFAULTS = {
    'delivery_area': 'NL',
    'currency': 'EUR',
    'timezone': 'CET',
    'fetch_interval_minutes': 60,
    'import_vat_multiplier': 1.21,
    'import_markup': 0.0248,
    'import_energy_tax': 0.1228,
    'export_vat_multiplier': 1.21,
    'export_markup': 0.0248,
    'export_energy_tax': 0.1228,
}

EP_REQUIRED_FIELDS = ['delivery_area', 'currency', 'timezone', 'fetch_interval_minutes']

# Old entities to clean up on startup (REST API mode only)
OLD_ENTITIES = [
    'sensor.ep_price_import',
    'sensor.ep_price_export', 
    'sensor.ep_price_level',
    'sensor.energy_price_import',
    'sensor.energy_price_export',
    'sensor.energy_price_level',
]


def load_config() -> dict:
    """Load Energy Prices configuration.
    
    Returns:
        Configuration dictionary
    """
    config = load_addon_config(
        defaults=EP_CONFIG_DEFAULTS,
        required_fields=EP_REQUIRED_FIELDS
    )
    
    logger.info("Loaded configuration: area=%s, currency=%s, timezone=%s, interval=%dm",
               config['delivery_area'], config['currency'], config['timezone'], 
               config['fetch_interval_minutes'])
    logger.info("Import: VAT=%.2f, markup=%.4f, tax=%.4f",
               config['import_vat_multiplier'], config['import_markup'], config['import_energy_tax'])
    logger.info("Export: VAT=%.2f, markup=%.4f, tax=%.4f",
               config['export_vat_multiplier'], config['export_markup'], config['export_energy_tax'])
    
    return config


def calculate_final_price(market_price: float, vat_multiplier: float, markup: float, energy_tax: float) -> float:
    """Calculate final price from market price and components.
    
    Formula: (market_price * vat_multiplier) + markup + energy_tax
    
    Args:
        market_price: Market price in EUR/kWh
        vat_multiplier: VAT multiplier (e.g., 1.21 for 21% VAT)
        markup: Fixed markup in EUR/kWh
        energy_tax: Energy tax in EUR/kWh
        
    Returns:
        Final price in EUR/kWh rounded to 4 decimals
    """
    result = (market_price * vat_multiplier) + markup + energy_tax
    return round(result, 4)


def fetch_and_process_prices(nordpool: NordPoolApi, config: dict) -> Optional[dict]:
    """Fetch prices, apply price components, calculate percentiles.
    
    Args:
        nordpool: Nord Pool API client
        config: Configuration dictionary with price component fields
        
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
        
        # Extract price components from config
        import_vat = config['import_vat_multiplier']
        import_markup = config['import_markup']
        import_tax = config['import_energy_tax']
        export_vat = config['export_vat_multiplier']
        export_markup = config['export_markup']
        export_tax = config['export_energy_tax']
        
        # Calculate final prices using component formula
        import_prices = []
        export_prices = []
        price_curve_import = []
        price_curve_export = []
        
        for interval in all_intervals:
            market_price = interval.price_eur_kwh()
            
            import_price = calculate_final_price(market_price, import_vat, import_markup, import_tax)
            export_price = calculate_final_price(market_price, export_vat, export_markup, export_tax)
            
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
        
        logger.info("Current import price: %.4f EUR/kWh, level: %s", 
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


def update_ha_entities(data: dict, ha_api: HomeAssistantApi, first_run: bool = False):
    """Update Home Assistant entities with price data.
    
    Args:
        data: Processed price data dictionary
        ha_api: HomeAssistantApi instance
        first_run: If True, log entity creation details (only on first run)
    """
    try:
        # Update sensor.ep_price_import
        ha_api.create_or_update_entity(
            'sensor.ep_price_import',
            str(data['current_import']),
            {
                'unit_of_measurement': 'EUR/kWh',
                'device_class': 'monetary',
                'friendly_name': 'Electricity Import Price',
                'price_curve': data['price_curve_import'],
                'percentiles': data['percentiles'],
                'last_update': data['last_update']
            },
            log_success=first_run
        )
        
        # Update sensor.ep_price_export
        ha_api.create_or_update_entity(
            'sensor.ep_price_export',
            str(data['current_export']),
            {
                'unit_of_measurement': 'EUR/kWh',
                'device_class': 'monetary',
                'friendly_name': 'Electricity Export Price',
                'price_curve': data['price_curve_export'],
                'last_update': data['last_update']
            },
            log_success=first_run
        )
        
        # Update sensor.ep_price_level
        ha_api.create_or_update_entity(
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
            log_success=first_run
        )
        
        # Log entity details on first run
        if first_run:
            logger.info("Created Home Assistant entities:")
            logger.info("  • sensor.ep_price_import: %.4f EUR/kWh (import price with VAT, markup, tax)", data['current_import'])
            logger.info("  • sensor.ep_price_export: %.4f EUR/kWh (export/feed-in price)", data['current_export'])
            logger.info("  • sensor.ep_price_level: %s (None/Low/Medium/High based on percentiles)", data['price_level'])
            logger.info("Each sensor includes price_curve attribute with %d intervals for today+tomorrow", 
                       len(data['price_curve_import']))
        else:
            logger.info("Updated entities: import=%.4f, export=%.4f, level=%s",
                       data['current_import'], data['current_export'], data['price_level'])
        
    except Exception as e:
        logger.error("Failed to update HA entities: %s", e, exc_info=True)


def update_ha_entities_mqtt(data: dict, mqtt_client: 'MqttDiscovery', first_run: bool = False):
    """Update Home Assistant entities via MQTT Discovery.
    
    This creates entities with proper unique_id support for UI management.
    
    Args:
        data: Processed price data dictionary
        mqtt_client: MQTT Discovery client
        first_run: If True, publish full discovery config; otherwise just state updates
    """
    try:
        if first_run:
            # Publish full discovery config on first run
            mqtt_client.publish_sensor(EntityConfig(
                object_id="price_import",
                name="Electricity Import Price",
                state=str(round(data['current_import'], 4)),
                unit_of_measurement="EUR/kWh",
                device_class="monetary",
                state_class="measurement",
                icon="mdi:currency-eur",
                attributes={
                    'price_curve': data['price_curve_import'],
                    'percentiles': data['percentiles'],
                    'last_update': data['last_update']
                }
            ))
            
            mqtt_client.publish_sensor(EntityConfig(
                object_id="price_export",
                name="Electricity Export Price",
                state=str(round(data['current_export'], 4)),
                unit_of_measurement="EUR/kWh",
                device_class="monetary",
                state_class="measurement",
                icon="mdi:currency-eur",
                attributes={
                    'price_curve': data['price_curve_export'],
                    'last_update': data['last_update']
                }
            ))
            
            mqtt_client.publish_sensor(EntityConfig(
                object_id="price_level",
                name="Electricity Price Level",
                state=data['price_level'],
                icon="mdi:gauge",
                attributes={
                    'current_price': data['current_import'],
                    'p20': data['percentiles']['p20'],
                    'p40': data['percentiles']['p40'],
                    'p60': data['percentiles']['p60'],
                    'classification_rules': 'None: <P20, Low: P20-P40, Medium: P40-P60, High: >=P60'
                }
            ))
            
            logger.info("Created Home Assistant entities via MQTT Discovery:")
            logger.info("  • sensor.energy_prices_price_import: %.4f EUR/kWh", data['current_import'])
            logger.info("  • sensor.energy_prices_price_export: %.4f EUR/kWh", data['current_export'])
            logger.info("  • sensor.energy_prices_price_level: %s", data['price_level'])
            logger.info("Entities have unique_id and can be managed from HA UI")
        else:
            # Just update state values
            mqtt_client.update_state("sensor", "price_import", 
                                     str(round(data['current_import'], 4)),
                                     {'price_curve': data['price_curve_import'],
                                      'percentiles': data['percentiles'],
                                      'last_update': data['last_update']})
            
            mqtt_client.update_state("sensor", "price_export",
                                     str(round(data['current_export'], 4)),
                                     {'price_curve': data['price_curve_export'],
                                      'last_update': data['last_update']})
            
            mqtt_client.update_state("sensor", "price_level",
                                     data['price_level'],
                                     {'current_price': data['current_import'],
                                      'p20': data['percentiles']['p20'],
                                      'p40': data['percentiles']['p40'],
                                      'p60': data['percentiles']['p60']})
            
            logger.info("Updated MQTT entities: import=%.4f, export=%.4f, level=%s",
                       data['current_import'], data['current_export'], data['price_level'])
        
    except Exception as e:
        logger.error("Failed to update HA entities via MQTT: %s", e, exc_info=True)


def main():
    """Main entry point for the add-on."""
    logger.info("Energy Prices add-on starting...")
    
    # Register signal handlers using shared module
    shutdown_event = setup_signal_handlers(logger)
    
    mqtt_client = None
    
    try:
        # Load configuration
        config = load_config()
        
        # Initialize API client
        nordpool = NordPoolApi()
        
        # Try MQTT Discovery first (provides unique_id for UI management)
        mqtt_client = setup_mqtt_client(
            addon_name="Energy Prices",
            addon_id="energy_prices",
            config=config,
            manufacturer="HA Addons",
            model="Nord Pool Price Monitor"
        )
        use_mqtt = mqtt_client is not None
        
        # Initialize HA API client as fallback
        ha_api = HomeAssistantApi()
        if not use_mqtt:
            if not ha_api.token:
                logger.warning("No HA API token set (SUPERVISOR_TOKEN/HA_API_TOKEN), entity updates will fail")
            logger.info("Using REST API fallback: %s", ha_api.base_url)
            # Delete old entities on startup to ensure clean state (REST API only)
            logger.info("Cleaning up old entities...")
            deleted = ha_api.delete_entities(OLD_ENTITIES)
            if deleted > 0:
                logger.info("Deleted %d old entities", deleted)
            else:
                logger.info("No old entities found to delete")
        
        fetch_interval = config['fetch_interval_minutes'] * 60
        run_once = get_run_once_mode()
        
        if run_once:
            logger.info("Running single iteration (RUN_ONCE mode)")
        else:
            logger.info("Starting main loop (fetch interval: %d minutes)", 
                       config['fetch_interval_minutes'])
        
        # Track first run for entity creation logging
        first_run = True
        
        # Main loop
        while not shutdown_event.is_set():
            try:
                # Fetch and process prices
                data = fetch_and_process_prices(nordpool, config)
                
                if data:
                    # Update HA entities via preferred method
                    if use_mqtt and mqtt_client and mqtt_client.is_connected():
                        update_ha_entities_mqtt(data, mqtt_client, first_run=first_run)
                    else:
                        update_ha_entities(data, ha_api, first_run=first_run)
                    first_run = False  # Only log creation details once
                else:
                    logger.warning("No price data to update entities")
                
            except Exception as e:
                logger.error("Error in main loop iteration: %s", e, exc_info=True)
            
            # Exit after first iteration if RUN_ONCE is set
            if run_once:
                logger.info("Single iteration complete, exiting")
                break
            
            # Sleep with shutdown check
            if not sleep_with_shutdown_check(shutdown_event, fetch_interval):
                break
        
    except Exception as e:
        logger.error("Fatal error in main: %s", e, exc_info=True)
        return 1
    finally:
        # Clean up MQTT connection
        if mqtt_client:
            mqtt_client.disconnect()
    
    logger.info("Energy Prices add-on stopped")
    return 0


if __name__ == "__main__":
    exit(main())
