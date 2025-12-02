#!/usr/bin/env python3
"""Run Water Heater Scheduler add-on locally for testing."""

import os
import sys
from pathlib import Path

# Load environment from .env file
try:
    from dotenv import load_dotenv
    # Check addon .env first, then parent .env
    addon_env = Path(__file__).parent / '.env'
    parent_env = Path(__file__).parent.parent / '.env'
    
    if addon_env.exists():
        load_dotenv(addon_env)
        print(f"Loaded environment from {addon_env}")
    elif parent_env.exists():
        load_dotenv(parent_env)
        print(f"Loaded environment from {parent_env}")
    else:
        print(f"No .env file found, using existing environment")
except ImportError:
    print("python-dotenv not installed, using existing environment")

# Add app directory to Python path
sys.path.insert(0, str(Path(__file__).parent))

# Import and run main
from app.main import main

if __name__ == '__main__':
    print("=" * 60)
    print("Water Heater Scheduler Add-on - Local Testing")
    print("=" * 60)
    print()
    
    # Display configuration
    print("Configuration:")
    print(f"  Water Heater Entity: {os.getenv('WATER_HEATER_ENTITY_ID', '(not set)')}")
    print(f"  Price Sensor: {os.getenv('PRICE_SENSOR_ENTITY_ID', 'sensor.ep_price_import')}")
    print(f"  Temperature Preset: {os.getenv('TEMPERATURE_PRESET', 'comfort')}")
    print(f"  Evaluation Interval: {os.getenv('EVALUATION_INTERVAL_MINUTES', '15')} minutes")
    print(f"  HA API URL: {os.getenv('HA_API_URL', '(not set)')}")
    print(f"  RUN_ONCE: {os.getenv('RUN_ONCE', '0')}")
    print()
    print("=" * 60)
    print()
    
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nInterrupted by user")
        sys.exit(0)
