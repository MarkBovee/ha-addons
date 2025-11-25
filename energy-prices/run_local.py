#!/usr/bin/env python3
"""Run Energy Prices add-on locally for testing."""

import os
import sys
from pathlib import Path

# Load environment from .env file
try:
    from dotenv import load_dotenv
    env_file = Path(__file__).parent / '.env'
    if env_file.exists():
        load_dotenv(env_file)
        print(f"Loaded environment from {env_file}")
    else:
        print(f"No .env file found at {env_file}, using existing environment")
except ImportError:
    print("python-dotenv not installed, using existing environment")

# Add app directory to Python path
app_dir = Path(__file__).parent / 'app'
sys.path.insert(0, str(app_dir.parent))

# Import and run main
from app.main import main

if __name__ == '__main__':
    print("=" * 60)
    print("Energy Prices Add-on - Local Testing")
    print("=" * 60)
    print()
    
    # Display configuration
    print("Configuration:")
    print(f"  Delivery Area: {os.getenv('DELIVERY_AREA', 'NL')}")
    print(f"  Currency: {os.getenv('CURRENCY', 'EUR')}")
    print(f"  Timezone: {os.getenv('TIMEZONE', 'CET')}")
    print(f"  Fetch Interval: {os.getenv('FETCH_INTERVAL_MINUTES', '60')} minutes")
    print(f"  HA API URL: {os.getenv('SUPERVISOR_TOKEN', '(not set)')[:20]}...")
    print()
    print("=" * 60)
    print()
    
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nInterrupted by user")
        sys.exit(0)
