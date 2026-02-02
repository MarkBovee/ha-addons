#!/usr/bin/env python3
"""Local runner for Battery Manager add-on."""

import os
import sys
from pathlib import Path


try:
    from dotenv import load_dotenv

    addon_env = Path(__file__).parent / ".env"
    parent_env = Path(__file__).parent.parent / ".env"

    if addon_env.exists():
        load_dotenv(addon_env)
        print(f"Loaded environment from {addon_env}")
    elif parent_env.exists():
        load_dotenv(parent_env)
        print(f"Loaded environment from {parent_env}")
    else:
        print("No .env file found, using existing environment")
except ImportError:
    print("python-dotenv not installed, using existing environment")

sys.path.insert(0, str(Path(__file__).parent))

from app.main import main  # noqa: E402


def _print_config_summary():
    print("=" * 60)
    print("Battery Manager Add-on - Local Testing")
    print("=" * 60)
    print()
    print("Configuration:")
    print(f"  HA API URL: {os.getenv('HA_API_URL', '(not set)')}")
    print(f"  HA API Token: {'SET' if os.getenv('HA_API_TOKEN') or os.getenv('SUPERVISOR_TOKEN') else 'NOT SET'}")
    print(f"  MQTT Host: {os.getenv('MQTT_HOST', 'core-mosquitto')}")
    print(f"  MQTT Port: {os.getenv('MQTT_PORT', '1883')}")
    print(f"  RUN_ONCE: {os.getenv('RUN_ONCE', '0')}")
    print()
    print("=" * 60)
    print()


if __name__ == "__main__":
    _print_config_summary()
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("Interrupted")
        sys.exit(130)
