#!/usr/bin/env python3
"""Local runner for Battery Strategy add-on."""

import os
import sys
from pathlib import Path

# Try to load .env
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
        print("Warning: No .env file found")

except ImportError:
    print("python-dotenv not installed, skipping .env loading")

# Add app to path
sys.path.insert(0, str(Path(__file__).parent))

# Run main
from app.main import main

if __name__ == "__main__":
    # Mock data location
    if "SUPERVISOR_TOKEN" not in os.environ and "HA_API_TOKEN" not in os.environ:
        print("Error: HA_API_TOKEN or SUPERVISOR_TOKEN must be set in .env")
        sys.exit(1)
        
    main()
