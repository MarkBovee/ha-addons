#!/usr/bin/env python3
"""Test script for schedule roundtrip (get, modify, set).

This script:
1. Authenticates with SAJ API
2. Gets the current schedule via getLeafMenu
3. Parses charge/discharge periods
4. Modifies one period (+1 minute to start time)
5. Sets the modified schedule back
6. Verifies by re-reading

Usage:
    python test_schedule_roundtrip.py

Requires .env file with:
    SAJ_USERNAME=your_username
    SAJ_PASSWORD=your_password  
    SAJ_DEVICE_SERIAL=HST2083J2446E06861
    SAJ_PLANT_UID=your_plant_uid
"""

import json
import logging
import os
import sys
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

# Add parent to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv

from app.saj_api import SajApiClient, _calc_signature, _generate_random_alphanumeric
from app.models import BatteryChargeType, ChargingPeriod

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)

# Parent ID for "Working modes" menu (from HAR capture)
WORKING_MODES_PARENT_ID = "8E3CEA8A-E149-4F72-AB50-3406B39F5ADB"


def get_schedule_from_api(client: SajApiClient) -> Dict[str, Any]:
    """Get current schedule configuration via getLeafMenu API.
    
    Args:
        client: Authenticated SAJ API client
        
    Returns:
        Full API response data
    """
    client._ensure_authenticated()
    
    url = f"{client.base_url}/dev-api/api/v1/remote/client/getLeafMenu"
    
    # Prepare signing parameters
    client_date = datetime.utcnow().strftime('%Y-%m-%d')
    timestamp = str(int(time.time() * 1000))
    random_str = _generate_random_alphanumeric(32)
    
    params = {
        'deviceSn': client.device_serial,
        'parentId': WORKING_MODES_PARENT_ID,
        'isParallelBatchSetting': '0',
        'appProjectName': 'elekeeper',
        'clientDate': client_date,
        'lang': 'en',
        'timeStamp': timestamp,
        'random': random_str,
        'clientId': 'esolar-monitor-admin',
    }
    signed = _calc_signature(params)
    
    logger.info("Fetching current schedule from SAJ API...")
    headers = {'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8'}
    response = client._session.post(url, data=signed, headers=headers)
    response.raise_for_status()
    
    result = response.json()
    if result.get('errCode') != 0:
        raise Exception(f"API error: {result.get('errMsg', 'Unknown error')}")
    
    return result


def parse_schedule_from_response(data: Dict[str, Any]) -> Dict[str, List[Dict]]:
    """Parse charge/discharge periods from getLeafMenu response.
    
    Args:
        data: API response data
        
    Returns:
        Dict with 'mode', 'charge' and 'discharge' lists
    """
    result = {
        'mode': None,
        'mode_name': None,
        'charge': [],
        'discharge': [],
    }
    
    items = data.get('data', [])
    
    for item in items:
        if item.get('commAddress') == '3647':
            # Working mode item
            meta_list = item.get('menuMetaList', [])
            if meta_list:
                meta = meta_list[0]
                result['mode'] = meta.get('actualVal_')
                result['mode_name'] = meta.get('actualName_')
                
                # Parse charge/discharge periods from menuMetaDetailList
                detail_list = meta.get('menuMetaDetailList', [])
                
                for detail in detail_list:
                    if detail.get('ifShow') not in ('1', 1, True):
                        # Only parse visible (active) periods
                        continue
                        
                    sub_details = detail.get('menuMetaDetailList', [])
                    if not sub_details:
                        continue
                    
                    # Extract period info
                    period = {}
                    weekdays = []
                    
                    for sub in sub_details:
                        title = sub.get('title_', '')
                        actual_val = sub.get('actualVal_', '')
                        actual_name = sub.get('actualName_', '')
                        
                        if 'Charge Time' in title or 'Discharge Time' in title:
                            if not period.get('start'):
                                period['start'] = actual_val
                            else:
                                period['end'] = actual_val
                            period['type'] = 'charge' if 'Charge' in title else 'discharge'
                        elif 'Power' in title:
                            period['power'] = int(actual_val) if actual_val else 0
                        elif 'Work Days' in title:
                            # Parse weekdays from nested structure
                            weekday_details = sub.get('menuMetaDetailList', [])
                            for wd in weekday_details:
                                weekdays.append(wd.get('actualVal_', '0'))
                    
                    if period.get('start') and period.get('type'):
                        period['weekdays'] = ','.join(weekdays) if weekdays else '1,1,1,1,1,1,1'
                        
                        # Calculate duration in minutes
                        if period.get('end'):
                            start_parts = period['start'].split(':')
                            end_parts = period['end'].split(':')
                            start_min = int(start_parts[0]) * 60 + int(start_parts[1])
                            end_min = int(end_parts[0]) * 60 + int(end_parts[1])
                            if end_min < start_min:
                                end_min += 24 * 60  # Handle midnight crossing
                            period['duration'] = end_min - start_min
                        
                        result[period['type']].append(period)
    
    return result


def add_minute_to_time(time_str: str) -> str:
    """Add 1 minute to a time string.
    
    Args:
        time_str: Time in HH:MM format
        
    Returns:
        New time string with 1 minute added
    """
    parts = time_str.split(':')
    hours = int(parts[0])
    mins = int(parts[1])
    
    mins += 1
    if mins >= 60:
        mins = 0
        hours = (hours + 1) % 24
    
    return f"{hours:02d}:{mins:02d}"


def main():
    """Main test function."""
    # Load environment
    load_dotenv()
    
    username = os.getenv('SAJ_USERNAME')
    password = os.getenv('SAJ_PASSWORD')
    device_serial = os.getenv('SAJ_DEVICE_SERIAL')
    plant_uid = os.getenv('SAJ_PLANT_UID')
    
    if not all([username, password, device_serial, plant_uid]):
        logger.error("Missing required environment variables!")
        logger.error("Required: SAJ_USERNAME, SAJ_PASSWORD, SAJ_DEVICE_SERIAL, SAJ_PLANT_UID")
        sys.exit(1)
    
    # Create client
    client = SajApiClient(
        username=username,
        password=password,
        device_serial=device_serial,
        plant_uid=plant_uid,
        token_file='./test-saj-token.json',
    )
    
    try:
        # Step 1: Authenticate
        logger.info("=" * 60)
        logger.info("STEP 1: Authenticating...")
        client.authenticate()
        logger.info("✅ Authentication successful")
        
        # Step 2: Get current schedule
        logger.info("=" * 60)
        logger.info("STEP 2: Getting current schedule...")
        response = get_schedule_from_api(client)
        schedule = parse_schedule_from_response(response)
        
        logger.info(f"Current mode: {schedule['mode_name']} (value={schedule['mode']})")
        logger.info(f"Charge periods: {len(schedule['charge'])}")
        for i, p in enumerate(schedule['charge']):
            logger.info(f"  [{i}] {p['start']} - {p.get('end', '?')} @ {p.get('power', 0)}W")
        logger.info(f"Discharge periods: {len(schedule['discharge'])}")
        for i, p in enumerate(schedule['discharge']):
            logger.info(f"  [{i}] {p['start']} - {p.get('end', '?')} @ {p.get('power', 0)}W")
        
        # Step 3: Modify first charge period (+1 minute)
        logger.info("=" * 60)
        logger.info("STEP 3: Modifying schedule...")
        
        if not schedule['charge']:
            logger.warning("No charge periods found, creating a test period...")
            # Create a test schedule with one charge period
            test_periods = [
                ChargingPeriod(
                    charge_type=BatteryChargeType.CHARGE,
                    start_time="02:00",
                    duration_minutes=60,
                    power_w=3000,
                )
            ]
        else:
            # Modify existing: add 1 minute to start time
            original_start = schedule['charge'][0]['start']
            new_start = add_minute_to_time(original_start)
            duration = schedule['charge'][0].get('duration', 60)
            power = schedule['charge'][0].get('power', 3000)
            
            logger.info(f"Modifying charge[0]: {original_start} -> {new_start}")
            
            test_periods = [
                ChargingPeriod(
                    charge_type=BatteryChargeType.CHARGE,
                    start_time=new_start,
                    duration_minutes=duration,
                    power_w=power,
                )
            ]
        
        # Step 4: Apply modified schedule
        logger.info("=" * 60)
        logger.info("STEP 4: Applying modified schedule...")
        
        success = client.save_schedule(test_periods)
        if success:
            logger.info("✅ Schedule applied successfully!")
        else:
            logger.error("❌ Failed to apply schedule")
            sys.exit(1)
        
        # Step 5: Verify by re-reading
        logger.info("=" * 60)
        logger.info("STEP 5: Verifying changes (waiting 3s for propagation)...")
        time.sleep(3)
        
        response2 = get_schedule_from_api(client)
        schedule2 = parse_schedule_from_response(response2)
        
        logger.info(f"Updated charge periods: {len(schedule2['charge'])}")
        for i, p in enumerate(schedule2['charge']):
            logger.info(f"  [{i}] {p['start']} - {p.get('end', '?')} @ {p.get('power', 0)}W")
        
        # Compare
        if schedule2['charge'] and test_periods:
            expected_start = test_periods[0].start_time
            actual_start = schedule2['charge'][0]['start']
            if expected_start == actual_start:
                logger.info(f"✅ Verification passed! Start time is {actual_start}")
            else:
                logger.warning(f"⚠️ Start time mismatch: expected {expected_start}, got {actual_start}")
        
        logger.info("=" * 60)
        logger.info("TEST COMPLETE")
        
    except Exception as e:
        logger.error(f"Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
