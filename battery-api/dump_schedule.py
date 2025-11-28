#!/usr/bin/env python3
"""Quick script to dump full schedule from SAJ API."""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

from app.saj_api import SajApiClient

client = SajApiClient(
    username=os.getenv('SAJ_USERNAME'),
    password=os.getenv('SAJ_PASSWORD'),
    device_serial=os.getenv('SAJ_DEVICE_SERIAL'),
    plant_uid=os.getenv('SAJ_PLANT_UID'),
    token_file='./test-saj-token.json',
)
client.authenticate()

schedule = client.get_schedule()
print("Current schedule (same format as input):")
print(json.dumps(schedule, indent=2))
