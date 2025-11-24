#!/usr/bin/env python3
"""Local debug script for running the EV Charger Monitor addon outside of Docker.

This script allows you to run the addon locally for development and testing.
It supports loading configuration from environment variables or a .env file.
"""

import os
import sys
from pathlib import Path

# Try to load python-dotenv if available (optional dependency)
try:
    from dotenv import load_dotenv
    DOTENV_AVAILABLE = True
except ImportError:
    DOTENV_AVAILABLE = False


def load_env_file():
    """Load environment variables from .env file if it exists."""
    if DOTENV_AVAILABLE:
        env_path = Path(__file__).parent / ".env"
        if env_path.exists():
            load_dotenv(env_path)
            print(f"Loaded environment variables from {env_path}")
            return True
        else:
            print("No .env file found. Using system environment variables.")
            return False
    else:
        # Manual .env parsing if python-dotenv is not available
        env_path = Path(__file__).parent / ".env"
        if env_path.exists():
            print(f"Loading .env file manually (python-dotenv not installed)")
            with open(env_path, "r") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        key, value = line.split("=", 1)
                        key = key.strip()
                        value = value.strip().strip('"').strip("'")
                        os.environ[key] = value
            return True
        else:
            print("No .env file found. Using system environment variables.")
            return False


def validate_config():
    """Validate that all required configuration is present."""
    required_vars = [
        "CHARGER_EMAIL",
        "CHARGER_PASSWORD",
        "HA_API_TOKEN",
    ]
    
    missing_vars = []
    for var in required_vars:
        if not os.environ.get(var):
            missing_vars.append(var)
    
    if missing_vars:
        print("ERROR: Missing required environment variables:")
        for var in missing_vars:
            print(f"  - {var}")
        print("\nPlease set these variables or create a .env file.")
        print("See .env.example for a template.")
        return False
    
    return True


def print_config_summary():
    """Print a summary of the current configuration (without sensitive data)."""
    print("\n" + "=" * 60)
    print("EV Charger Monitor - Local Debug Mode")
    print("=" * 60)
    print(f"Email: {os.environ.get('CHARGER_EMAIL', 'NOT SET')}")
    print(f"Host Name: {os.environ.get('CHARGER_HOST_NAME', 'my.charge.space (default)')}")
    print(f"Base URL: {os.environ.get('CHARGER_BASE_URL', 'https://my.charge.space (default)')}")
    print(f"Update Interval: {os.environ.get('CHARGER_UPDATE_INTERVAL', '1 (default)')} minutes")
    print(f"HA API URL: {os.environ.get('HA_API_URL', 'http://localhost:8123/api (default)')}")
    print(f"HA API Token: {'SET' if os.environ.get('HA_API_TOKEN') else 'NOT SET'}")
    print("=" * 60 + "\n")


def main():
    """Main entry point for local debug script."""
    # Load .env file if available
    load_env_file()
    
    # Validate configuration
    if not validate_config():
        sys.exit(1)
    
    # Print configuration summary
    print_config_summary()
    
    # Import and run the main application
    try:
        from app.main import main as app_main
        app_main()
    except KeyboardInterrupt:
        print("\n\nShutdown requested by user. Exiting...")
        sys.exit(0)
    except Exception as e:
        print(f"\n\nERROR: Failed to start application: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

