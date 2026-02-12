#!/usr/bin/env python3
"""Monitor Battery Manager sensors."""

import os
import sys
import requests
import json
from pathlib import Path

try:
    from dotenv import load_dotenv
    env_file = Path(__file__).parent / ".env"
    if env_file.exists():
        load_dotenv(env_file)
except ImportError:
    pass

token = os.getenv('HA_API_TOKEN') or os.getenv('SUPERVISOR_TOKEN')
base_url = os.getenv('HA_API_URL', 'http://192.168.1.135:8123/api')
headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}

sensors = [
    'sensor.bm_status',
    'sensor.bm_reasoning',
    'sensor.bm_forecast',
    'sensor.bm_price_ranges',
    'sensor.bm_current_action',
    'sensor.bm_charge_schedule',
    'sensor.bm_discharge_schedule',
    'sensor.bm_schedule',
    'sensor.bm_mode'
]

print('=' * 80)
print('BATTERY MANAGER SENSORS STATUS')
print('=' * 80)
print()

for sensor in sensors:
    try:
        resp = requests.get(f'{base_url}/states/{sensor}', headers=headers, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            state = data.get('state', 'unknown')
            attrs = data.get('attributes', {})
            print(f'📊 {sensor}')
            print(f'   State: {state}')
            if attrs:
                for key, value in attrs.items():
                    if key not in ['friendly_name', 'icon', 'device_class', 'unit_of_measurement']:
                        if isinstance(value, dict):
                            print(f'   {key}:')
                            for k, v in value.items():
                                print(f'      {k}: {v}')
                        elif isinstance(value, str) and '\n' in value:
                            print(f'   {key}:')
                            for line in value.split('\n'):
                                print(f'      {line}')
                        else:
                            print(f'   {key}: {value}')
            print()
        else:
            print(f'❌ {sensor}: Not found (status {resp.status_code})')
            print()
    except Exception as e:
        print(f'❌ {sensor}: Error - {e}')
        print()
