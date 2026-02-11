#!/usr/bin/env python3
"""Check Battery Manager add-on logs."""

import os
import sys
import requests
from pathlib import Path

try:
    from dotenv import load_dotenv
    env_file = Path(__file__).parent / ".env"
    if env_file.exists():
        load_dotenv(env_file)
except ImportError:
    pass

token = os.getenv('SUPERVISOR_TOKEN') or os.getenv('HA_API_TOKEN')
supervisor_url = 'http://supervisor'

# Try to get addon info first
headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}

print('=' * 80)
print('BATTERY MANAGER ADD-ON STATUS')
print('=' * 80)
print()

try:
    # Get addon info
    resp = requests.get(f'{supervisor_url}/addons/local_battery_manager/info', 
                       headers=headers, timeout=10)
    if resp.status_code == 200:
        data = resp.json()['data']
        print(f"State: {data.get('state', 'unknown')}")
        print(f"Boot: {data.get('boot', 'unknown')}")
        print(f"Version: {data.get('version', 'unknown')}")
        print()
    else:
        print(f"Cannot get addon info: {resp.status_code}")
        print()
except Exception as e:
    print(f"Error getting addon info: {e}")
    print()

# Get recent logs
try:
    resp = requests.get(f'{supervisor_url}/addons/local_battery_manager/logs',
                       headers=headers, timeout=10)
    if resp.status_code == 200:
        logs = resp.text
        lines = logs.split('\n')
        print("=" * 80)
        print("RECENT LOGS (last 50 lines)")
        print("=" * 80)
        for line in lines[-50:]:
            if line.strip():
                print(line)
    else:
        print(f"Cannot get logs: {resp.status_code}")
except Exception as e:
    print(f"Error getting logs: {e}")
