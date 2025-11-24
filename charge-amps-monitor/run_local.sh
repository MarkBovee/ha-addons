#!/bin/bash
# Local debug script for Linux/Mac
# This script helps set up environment variables and run the addon locally

# Check if .env file exists
if [ -f .env ]; then
    echo "Loading environment variables from .env file..."
    export $(cat .env | grep -v '^#' | xargs)
else
    echo "No .env file found. Using system environment variables."
    echo "You can create a .env file based on .env.example"
fi

# Set default values if not already set
export CHARGER_HOST_NAME="${CHARGER_HOST_NAME:-my.charge.space}"
export CHARGER_BASE_URL="${CHARGER_BASE_URL:-https://my.charge.space}"
export CHARGER_UPDATE_INTERVAL="${CHARGER_UPDATE_INTERVAL:-1}"
export HA_API_URL="${HA_API_URL:-http://localhost:8123/api}"

# Check if Python 3 is available
if ! command -v python3 &> /dev/null; then
    echo "ERROR: python3 is not installed or not in PATH"
    exit 1
fi

# Run the local debug script
python3 run_local.py

