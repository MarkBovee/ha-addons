"""SAJ Electric Cloud API client.

Port of the C# BatteryApi.cs from NetDaemonApps to Python.
Handles authentication, token management, and schedule operations.
"""

import hashlib
import json
import logging
import os
import random
import string
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlencode

import requests
from Crypto.Cipher import AES

from .models import (
    BatteryChargeType,
    BatteryScheduleParameters,
    BatteryUserMode,
    ChargingPeriod,
    build_schedule_parameters,
)

logger = logging.getLogger(__name__)

# SAJ API constants (from HAR analysis)
PASSWORD_ENCRYPTION_KEY = "ec1840a7c53cf0709eb784be480379b6"
QUERY_SIGN_KEY = "ktoKRLgQPjvNyUZO8lVc9kU1Bsip6XIe"
DEFAULT_OPER_TYPE = 15
DEFAULT_IS_PARALLEL_BATCH_SETTING = 0
DEFAULT_APP_PROJECT_NAME = "elekeeper"
DEFAULT_LANG = "en"
CLIENT_ID = "esolar-monitor-admin"
BASE_URL = "https://eop.saj-electric.com"

# Battery mode register address (from HAR analysis)
MODE_COMM_ADDRESS = "3647|3647"
# Mode values: 0 = Self-consumption, 1 = Time-of-use, 12 = AI mode
MODE_VALUE_SELF_CONSUMPTION = "0|0"
MODE_VALUE_TIME_OF_USE = "1|1"
MODE_VALUE_AI = "12|12"

# Token refresh buffer (refresh 24h before expiry)
REFRESH_BEFORE_EXPIRY = timedelta(hours=24)

# Token storage file path
TOKEN_FILE = "/data/saj-token.json"


def _generate_random_alphanumeric(length: int = 32) -> str:
    """Generate a random alphanumeric string."""
    chars = string.ascii_letters + string.digits
    return ''.join(random.choice(chars) for _ in range(length))


def _hex_to_bytes(hex_string: str) -> bytes:
    """Convert hex string to bytes."""
    return bytes.fromhex(hex_string)


def _pkcs7_pad(data: bytes, block_size: int = 16) -> bytes:
    """Apply PKCS7 padding to data."""
    pad_len = block_size - (len(data) % block_size)
    return data + bytes([pad_len] * pad_len)


def _encrypt_password(password: str) -> str:
    """Encrypt password using AES-ECB with PKCS7 padding.
    
    Matches the Elekeeper API's password encryption (Python/JS compatible).
    
    Args:
        password: Plain text password
        
    Returns:
        Encrypted password as lowercase hex string
    """
    key = _hex_to_bytes(PASSWORD_ENCRYPTION_KEY)
    plain_bytes = password.encode('utf-8')
    padded = _pkcs7_pad(plain_bytes, 16)
    
    cipher = AES.new(key, AES.MODE_ECB)
    encrypted = cipher.encrypt(padded)
    
    return encrypted.hex().lower()


def _sha1_hex_custom(input_string: str) -> str:
    """Custom SHA1-to-hex conversion matching Elekeeper JS/Python.
    
    Note: This uses no zero-padding on nibbles, which matches the C# implementation.
    """
    sha1_hash = hashlib.sha1(input_string.encode('utf-8')).digest()
    result = []
    for byte in sha1_hash:
        result.append(format(byte >> 4, 'x'))  # high nibble, no padding
        result.append(format(byte & 0xF, 'x'))  # low nibble, no padding
    return ''.join(result)


def _calc_signature(params: Dict[str, str]) -> Dict[str, str]:
    """Calculate signature for Elekeeper API.
    
    Signs a dictionary of parameters using MD5 + SHA1 (matches Elekeeper Python/JS).
    
    Args:
        params: Dictionary of parameters to sign
        
    Returns:
        Updated dictionary with 'signature' and 'signParams' added
    """
    # Sort keys alphabetically
    sorted_keys = sorted(params.keys())
    keys_str = ','.join(sorted_keys)
    
    # Build sorted parameter string
    sorted_string = '&'.join(f"{k}={params[k]}" for k in sorted_keys)
    sign_string = sorted_string + "&key=" + QUERY_SIGN_KEY
    
    # MD5 hash (using ISO-8859-1 encoding for compatibility)
    md5_hash = hashlib.md5(sign_string.encode('iso-8859-1')).hexdigest().lower()
    
    # Custom SHA1 hash
    signature = _sha1_hex_custom(md5_hash).upper()
    
    # Add signature fields to params
    params['signature'] = signature
    params['signParams'] = keys_str
    
    return params


class SajApiClient:
    """SAJ Electric Cloud API client.
    
    Handles authentication, token management, and battery schedule operations.
    """
    
    def __init__(
        self,
        username: str,
        password: str,
        device_serial: str,
        plant_uid: str,
        base_url: str = BASE_URL,
        simulation_mode: bool = False,
        token_file: str = TOKEN_FILE,
    ):
        """Initialize SAJ API client.
        
        Args:
            username: SAJ account username
            password: SAJ account password
            device_serial: Device serial number
            plant_uid: Plant UID
            base_url: API base URL (default: SAJ Electric)
            simulation_mode: If True, log API calls but don't execute
            token_file: Path to store token for persistence
        """
        self.username = username
        self.password = password
        self.device_serial = device_serial
        self.plant_uid = plant_uid
        self.base_url = base_url.rstrip('/')
        self.simulation_mode = simulation_mode
        self.token_file = token_file
        
        self._token: Optional[str] = None
        self._token_expiration: Optional[datetime] = None
        
        # HTTP session with default headers
        self._session = requests.Session()
        self._session.timeout = 120  # 2 minute timeout
        
    @property
    def is_configured(self) -> bool:
        """Check if the client has valid configuration."""
        return bool(
            self.username and
            self.password and
            self.device_serial and
            self.plant_uid
        )
    
    def _read_token_from_file(self) -> bool:
        """Read stored token from file.
        
        Returns:
            True if valid token was loaded
        """
        if not os.path.exists(self.token_file):
            return False
        
        try:
            with open(self.token_file, 'r') as f:
                data = json.load(f)
            
            self._token = data.get('token')
            
            # Parse expiry time
            if 'expires_at_utc' in data:
                self._token_expiration = datetime.fromisoformat(
                    data['expires_at_utc'].replace('Z', '+00:00')
                ).replace(tzinfo=None)
            elif 'expiresAtUtc' in data:
                # Backwards compatibility with C# format
                self._token_expiration = datetime.fromisoformat(
                    data['expiresAtUtc'].replace('Z', '+00:00')
                ).replace(tzinfo=None)
            elif 'expires_in' in data:
                # Compute from file modification time
                file_time = datetime.utcfromtimestamp(os.path.getmtime(self.token_file))
                self._token_expiration = file_time + timedelta(seconds=data['expires_in'])
            
            return bool(self._token)
            
        except Exception as e:
            logger.warning("Error reading token file: %s", e)
            return False
    
    def _write_token_to_file(self, token: str, expires_in: int):
        """Write token to file for persistence.
        
        Args:
            token: The API token
            expires_in: Token validity in seconds
        """
        try:
            expires_at_utc = datetime.utcnow() + timedelta(seconds=expires_in)
            data = {
                'token': token,
                'expires_in': expires_in,
                'expires_at_utc': expires_at_utc.isoformat() + 'Z',
            }
            
            # Atomic write using temp file
            tmp_file = self.token_file + '.tmp'
            os.makedirs(os.path.dirname(self.token_file) or '.', exist_ok=True)
            
            with open(tmp_file, 'w') as f:
                json.dump(data, f)
            
            os.replace(tmp_file, self.token_file)
            logger.info("Token saved, expires at %s", expires_at_utc.isoformat())
            
        except Exception as e:
            logger.warning("Error writing token file: %s", e)
    
    def _set_auth_headers(self, token: Optional[str] = None):
        """Set authentication headers on the session.
        
        Args:
            token: Token to use (uses self._token if not provided)
        """
        token = token or self._token
        if not token:
            return
        
        self._session.headers['Authorization'] = f'Bearer {token}'
        self._session.cookies.set('SAJ-token', token)
    
    def _ensure_authenticated(self) -> str:
        """Ensure we have a valid authentication token.
        
        Returns:
            Valid authentication token
            
        Raises:
            Exception: If authentication fails
        """
        now = datetime.utcnow()
        
        # Try to load existing token
        if self._read_token_from_file() and self._token and self._token_expiration:
            time_left = self._token_expiration - now
            
            # Token still valid and not close to expiry
            if self._token_expiration > now and time_left > REFRESH_BEFORE_EXPIRY:
                self._set_auth_headers()
                return self._token
            
            # Token valid but close to expiry - try to refresh
            if self._token_expiration > now and time_left > timedelta(0):
                logger.info("Token expiring in %s, proactively refreshing", time_left)
                try:
                    return self.authenticate()
                except Exception as e:
                    logger.warning("Proactive refresh failed, using existing token: %s", e)
                    self._set_auth_headers()
                    return self._token
        
        # No valid token, authenticate fresh
        return self.authenticate()
    
    def authenticate(self) -> str:
        """Authenticate with SAJ API and obtain token.
        
        Returns:
            Authentication token
            
        Raises:
            Exception: If authentication fails
        """
        if self.simulation_mode:
            logger.info("SIMULATION: Would authenticate with SAJ API")
            self._token = "simulation-token"
            self._token_expiration = datetime.utcnow() + timedelta(days=1)
            return self._token
        
        url = f"{self.base_url}/dev-api/api/v1/sys/login"
        
        # Set request headers
        headers = {
            'lang': 'en',
            'Accept': 'application/json, text/plain, */*',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:142.0) Gecko/20100101 Firefox/142.0',
            'Origin': 'https://eop.saj-electric.com',
            'Accept-Language': 'en-US,en;q=0.5',
            'enableSign': 'false',
            'DNT': '1',
            'Sec-GPC': '1',
            'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
        }
        
        # Prepare signing parameters
        client_date = datetime.utcnow().strftime('%Y-%m-%d')
        timestamp = str(int(time.time() * 1000))
        random_str = _generate_random_alphanumeric(32)
        
        sign_params = {
            'appProjectName': DEFAULT_APP_PROJECT_NAME,
            'clientDate': client_date,
            'lang': DEFAULT_LANG,
            'timeStamp': timestamp,
            'random': random_str,
            'clientId': CLIENT_ID,
        }
        signed = _calc_signature(sign_params.copy())
        
        # Build form data
        form_data = {
            'lang': DEFAULT_LANG,
            'password': _encrypt_password(self.password),
            'rememberMe': 'true',
            'username': self.username,
            'loginType': '1',
            'appProjectName': DEFAULT_APP_PROJECT_NAME,
            'clientDate': client_date,
            'timeStamp': timestamp,
            'random': random_str,
            'clientId': CLIENT_ID,
            'signParams': signed['signParams'],
            'signature': signed['signature'],
        }
        
        logger.debug("Authenticating to SAJ API...")
        response = self._session.post(url, data=form_data, headers=headers)
        response.raise_for_status()
        
        result = response.json()
        
        if 'data' in result and 'token' in result['data']:
            data = result['data']
            token_head = data.get('tokenHead', '')
            token_value = data.get('token', '')
            
            # Remove Bearer prefix if present
            if token_head and token_head.strip().lower().startswith('bearer'):
                token_head = ''
            
            self._token = (token_head or '') + (token_value or '')
            expires_in = data.get('expiresIn', 86400)
            self._token_expiration = datetime.utcnow() + timedelta(seconds=expires_in)
            
            self._set_auth_headers()
            self._write_token_to_file(self._token, expires_in)
            
            logger.info("Authenticated successfully, token valid until %s", self._token_expiration)
            return self._token
        else:
            error_msg = result.get('errMsg', 'Unknown error')
            raise Exception(f"Authentication failed: {error_msg}")
    
    def get_energy_flow_data(self) -> Dict[str, Any]:
        """Get energy flow data from the inverter (battery, solar, grid, load).
        
        Returns dict with:
            - battery_soc: Battery state of charge (%)
            - battery_power: Battery power (W, positive=charging)
            - battery_direction: 1=charging, -1=discharging, 0=idle
            - pv_power: Solar PV power (W)
            - grid_power: Grid power (W, positive=importing)
            - grid_direction: 1=importing, -1=exporting, 0=none
            - load_power: Total load power (W)
            - user_mode: Mode name string
            - update_time: Last update timestamp
        """
        if self.simulation_mode:
            logger.info("SIMULATION: Would get energy flow from SAJ API")
            return {
                'battery_soc': 75,
                'battery_power': 500,
                'battery_direction': 1,
                'pv_power': 3000,
                'grid_power': 0,
                'grid_direction': 0,
                'load_power': 2500,
                'user_mode': 'TimeOfUse',
                'update_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            }
        
        self._ensure_authenticated()
        
        url = f"{self.base_url}/dev-api/api/v1/monitor/home/getDeviceEneryFlowData"
        
        # Prepare signing parameters
        client_date = datetime.utcnow().strftime('%Y-%m-%d')
        timestamp = str(int(time.time() * 1000))
        random_str = _generate_random_alphanumeric(32)
        
        params = {
            'plantUid': self.plant_uid,
            'deviceSn': self.device_serial,
            'appProjectName': DEFAULT_APP_PROJECT_NAME,
            'clientDate': client_date,
            'lang': DEFAULT_LANG,
            'timeStamp': timestamp,
            'random': random_str,
            'clientId': CLIENT_ID,
        }
        signed = _calc_signature(params)
        
        try:
            response = self._session.get(url, params=signed)
            response.raise_for_status()
            
            result = response.json()
            
            if result.get('errCode') == 0:
                data = result.get('data', {})
                
                # Parse battery direction for signed power
                bat_direction = data.get('batteryDirection', 0)
                bat_power_raw = data.get('batPower', 0) or 0
                # batteryDirection > 0 = discharging (positive), < 0 = charging (negative)
                battery_power = bat_power_raw if bat_direction >= 0 else -bat_power_raw
                
                # Parse grid direction for signed power  
                grid_direction = data.get('gridDirection', 0)
                grid_power_raw = data.get('sysGridPowerwatt', 0) or 0
                # gridDirection: 1=importing, -1=exporting
                grid_power = grid_power_raw if grid_direction >= 0 else -grid_power_raw
                
                flow_data = {
                    'battery_soc': data.get('batEnergyPercent'),
                    'battery_power': battery_power,
                    'battery_direction': bat_direction,
                    'battery_capacity': data.get('batCapacity'),
                    'battery_current': data.get('batCurrent'),
                    'battery_charge_today': data.get('batChargeToday'),  # Wh
                    'battery_discharge_today': data.get('batDischargeToday'),  # Wh
                    'battery_charge_total': data.get('batChargeTotal'),  # Wh
                    'battery_discharge_total': data.get('batDischargeTotal'),  # Wh
                    'pv_power': data.get('totalPvPower', 0) or 0,
                    'pv_direction': data.get('pvDirection'),
                    'solar_power': data.get('solarPower'),  # Alternative PV field
                    'grid_power': grid_power,
                    'grid_direction': grid_direction,
                    'load_power': data.get('totalLoadPowerwatt', 0) or 0,
                    'home_load_power': data.get('homeLoadPower'),
                    'backup_load_power': data.get('backupLoadPower'),
                    'input_output_power': data.get('inputOutputPower'),
                    'output_direction': data.get('outputDirection'),
                    'user_mode': data.get('userModeName'),
                    'update_time': data.get('updateDate'),
                    # Device info
                    'plant_name': data.get('plantName'),
                    'inverter_model': data.get('devModel'),
                    'inverter_sn': data.get('devSn'),
                }
                
                logger.debug("Energy flow: SOC=%.1f%%, bat=%.0fW, pv=%.0fW, grid=%.0fW, load=%.0fW",
                            flow_data['battery_soc'] or 0,
                            flow_data['battery_power'],
                            flow_data['pv_power'],
                            flow_data['grid_power'],
                            flow_data['load_power'])
                return flow_data
            else:
                error_msg = result.get('errMsg', 'Unknown error')
                logger.error("Failed to get energy flow: %s", error_msg)
                return {}
                
        except Exception as e:
            logger.error("Exception getting energy flow: %s", e)
            return {}
    
    def get_user_mode(self) -> Optional[str]:
        """Get the current user mode from the inverter.
        
        Returns:
            User mode string (e.g., 'EMS', 'TimeOfUse'), or None on failure
        """
        # Use the energy flow data which includes mode
        data = self.get_energy_flow_data()
        return data.get('user_mode')
    
    def get_schedule(self) -> Dict[str, Any]:
        """Get the current battery schedule from the inverter.
        
        Returns schedule in the same format as the input JSON:
        {
            "mode": "time-of-use" | "self-consumption",
            "charge": [{"start": "HH:MM", "power": watts, "duration": minutes}, ...],
            "discharge": [{"start": "HH:MM", "power": watts, "duration": minutes}, ...]
        }
        
        Returns:
            Schedule dict, or empty dict on failure
        """
        if self.simulation_mode:
            logger.info("SIMULATION: Would get schedule from SAJ API")
            return {"mode": "time-of-use", "charge": [], "discharge": []}
        
        self._ensure_authenticated()
        
        url = f"{self.base_url}/dev-api/api/v1/remote/client/getLeafMenu"
        
        # Parent ID for "Working modes" menu (from HAR capture)
        working_modes_parent_id = "8E3CEA8A-E149-4F72-AB50-3406B39F5ADB"
        
        # Prepare signing parameters
        client_date = datetime.utcnow().strftime('%Y-%m-%d')
        timestamp = str(int(time.time() * 1000))
        random_str = _generate_random_alphanumeric(32)
        
        params = {
            'deviceSn': self.device_serial,
            'parentId': working_modes_parent_id,
            'isParallelBatchSetting': '0',
            'appProjectName': DEFAULT_APP_PROJECT_NAME,
            'clientDate': client_date,
            'lang': DEFAULT_LANG,
            'timeStamp': timestamp,
            'random': random_str,
            'clientId': CLIENT_ID,
        }
        signed = _calc_signature(params)
        
        try:
            headers = {'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8'}
            response = self._session.post(url, data=signed, headers=headers)
            response.raise_for_status()
            
            result = response.json()
            
            if result.get('errCode') != 0:
                error_msg = result.get('errMsg', 'Unknown error')
                logger.error("Failed to get schedule: %s", error_msg)
                return {}
            
            return self._parse_schedule_response(result)
            
        except Exception as e:
            logger.error("Exception getting schedule: %s", e)
            return {}
    
    def _parse_schedule_response(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Parse the getLeafMenu response into schedule format.
        
        Args:
            data: Raw API response
            
        Returns:
            Schedule dict with mode, charge, and discharge lists
        """
        result = {
            'mode': None,
            'charge': [],
            'discharge': [],
        }
        
        items = data.get('data', [])
        
        for item in items:
            if item.get('commAddress') != '3647':
                continue
                
            meta_list = item.get('menuMetaList', [])
            if not meta_list:
                continue
                
            meta = meta_list[0]
            
            # Parse mode
            mode_val = meta.get('actualVal_')
            if mode_val == '0':
                result['mode'] = 'self-consumption'
            elif mode_val == '1':
                result['mode'] = 'time-of-use'
            else:
                result['mode'] = meta.get('actualName_', 'unknown')
            
            # Parse periods from menuMetaDetailList
            detail_list = meta.get('menuMetaDetailList', [])
            
            for detail in detail_list:
                # Only parse visible (active) periods with ifShow=1
                if detail.get('ifShow') not in ('1', 1):
                    continue
                
                sub_details = detail.get('menuMetaDetailList', [])
                if not sub_details:
                    continue
                
                period = self._parse_period_details(sub_details)
                if period:
                    period_type = period.pop('type', None)
                    if period_type == 'charge':
                        result['charge'].append(period)
                    elif period_type == 'discharge':
                        result['discharge'].append(period)
        
        logger.debug("Parsed schedule: mode=%s, charge=%d, discharge=%d",
                    result['mode'], len(result['charge']), len(result['discharge']))
        
        return result
    
    def _parse_period_details(self, sub_details: List[Dict]) -> Optional[Dict]:
        """Parse period details from sub-menu items.
        
        Args:
            sub_details: List of sub-detail items
            
        Returns:
            Period dict with start, power, duration, type or None
        """
        start_time = None
        end_time = None
        power = 0
        period_type = None
        
        for sub in sub_details:
            title = sub.get('title_', '')
            actual_val = sub.get('actualVal_', '')
            
            if 'Charge Time' in title:
                if not start_time:
                    start_time = actual_val
                period_type = 'charge'
            elif 'Discharge Time' in title:
                if not start_time:
                    start_time = actual_val
                period_type = 'discharge'
            elif title == '' and actual_val and ':' in actual_val:
                # End time (has no title)
                end_time = actual_val
            elif 'Power' in title:
                try:
                    power = int(actual_val) if actual_val else 0
                except ValueError:
                    power = 0
        
        if not start_time or not period_type:
            return None
        
        # Calculate duration from start/end times
        duration = 60  # Default to 60 minutes
        if start_time and end_time:
            try:
                start_parts = start_time.split(':')
                end_parts = end_time.split(':')
                start_min = int(start_parts[0]) * 60 + int(start_parts[1])
                end_min = int(end_parts[0]) * 60 + int(end_parts[1])
                if end_min <= start_min:
                    end_min += 24 * 60  # Handle midnight crossing
                duration = end_min - start_min
            except (ValueError, IndexError):
                duration = 60
        
        return {
            'type': period_type,
            'start': start_time,
            'power': power,
            'duration': duration,
        }
    
    def save_schedule(self, periods: List[ChargingPeriod]) -> bool:
        """Save a battery schedule to the inverter.
        
        Args:
            periods: List of charging periods to schedule
            
        Returns:
            True if schedule was saved successfully
        """
        if not periods:
            logger.warning("No periods provided to save_schedule")
            return False
        
        # Build schedule parameters
        try:
            params = build_schedule_parameters(periods)
        except ValueError as e:
            logger.error("Invalid schedule parameters: %s", e)
            return False
        
        if self.simulation_mode:
            logger.info("SIMULATION: Would save schedule to SAJ API")
            logger.info("  CommAddress: %s", params.comm_address)
            logger.info("  ComponentId: %s", params.component_id)
            logger.info("  TransferId: %s", params.transfer_id)
            logger.info("  Value: %s", params.value)
            return True
        
        self._ensure_authenticated()
        
        url = f"{self.base_url}/dev-api/api/v1/remote/client/saveCommonParaRemoteSetting"
        
        # Prepare signing parameters
        client_date = datetime.utcnow().strftime('%Y-%m-%d')
        timestamp = str(int(time.time() * 1000))
        random_str = _generate_random_alphanumeric(32)
        
        sign_params = {
            'appProjectName': DEFAULT_APP_PROJECT_NAME,
            'clientDate': client_date,
            'lang': DEFAULT_LANG,
            'timeStamp': timestamp,
            'random': random_str,
            'clientId': CLIENT_ID,
        }
        signed = _calc_signature(sign_params)
        
        # Add schedule-specific parameters
        signed['deviceSn'] = self.device_serial
        signed['isParallelBatchSetting'] = str(DEFAULT_IS_PARALLEL_BATCH_SETTING)
        signed['commAddress'] = params.comm_address
        signed['componentId'] = params.component_id
        signed['operType'] = str(DEFAULT_OPER_TYPE)
        signed['transferId'] = params.transfer_id
        signed['value'] = params.value
        
        logger.debug("Saving schedule to SAJ API...")
        logger.debug("  CommAddress: %s", params.comm_address)
        logger.debug("  Value: %s", params.value)
        
        try:
            headers = {'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8'}
            response = self._session.post(url, data=signed, headers=headers)
            response.raise_for_status()
            
            result = response.json()
            err_code = result.get('errCode')
            
            if err_code == 0:
                logger.debug("Schedule saved to inverter")
                return True
            else:
                error_msg = result.get('errMsg', 'Unknown error')
                logger.error("Failed to save schedule: code=%s, msg=%s", err_code, error_msg)
                return False
                
        except Exception as e:
            logger.error("Exception saving schedule: %s", e)
            return False

    def set_battery_mode(self, mode: str) -> bool:
        """Set the battery operation mode.
        
        Args:
            mode: Mode to set - "self_consumption" or "time_of_use"
            
        Returns:
            True if mode was set successfully
        """
        mode_lower = mode.lower().replace("-", "_").replace(" ", "_")
        
        if mode_lower in ("self_consumption", "selfconsumption"):
            mode_value = MODE_VALUE_SELF_CONSUMPTION
            mode_name = "Self-consumption"
            component_id = "|0"
        elif mode_lower in ("time_of_use", "timeofuse", "tou"):
            mode_value = MODE_VALUE_TIME_OF_USE
            mode_name = "Time-of-use"
            component_id = "|0"
        elif mode_lower in ("ai", "ai_mode", "aimode"):
            mode_value = MODE_VALUE_AI
            mode_name = "AI"
            component_id = "|36"  # AI mode uses different componentId (from HAR)
        else:
            logger.error("Unknown battery mode: %s (expected 'self_consumption', 'time_of_use', or 'ai')", mode)
            return False
        
        if self.simulation_mode:
            logger.info("SIMULATION: Would set battery mode to %s", mode_name)
            return True
        
        self._ensure_authenticated()
        
        url = f"{self.base_url}/dev-api/api/v1/remote/client/saveCommonParaRemoteSetting"
        
        # Prepare signing parameters
        client_date = datetime.utcnow().strftime('%Y-%m-%d')
        timestamp = str(int(time.time() * 1000))
        random_str = _generate_random_alphanumeric(32)
        
        sign_params = {
            'appProjectName': DEFAULT_APP_PROJECT_NAME,
            'clientDate': client_date,
            'lang': DEFAULT_LANG,
            'timeStamp': timestamp,
            'random': random_str,
            'clientId': CLIENT_ID,
        }
        signed = _calc_signature(sign_params)
        
        # Add mode-specific parameters
        signed['deviceSn'] = self.device_serial
        signed['isParallelBatchSetting'] = str(DEFAULT_IS_PARALLEL_BATCH_SETTING)
        signed['commAddress'] = MODE_COMM_ADDRESS
        signed['componentId'] = component_id
        signed['operType'] = str(DEFAULT_OPER_TYPE)
        signed['transferId'] = "|"  # From HAR capture
        signed['value'] = mode_value
        
        logger.info("Setting battery mode to %s (value=%s)", mode_name, mode_value)
        
        try:
            headers = {'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8'}
            response = self._session.post(url, data=signed, headers=headers)
            response.raise_for_status()
            
            result = response.json()
            err_code = result.get('errCode')
            
            if err_code == 0:
                logger.info("Battery mode set to %s successfully", mode_name)
                return True
            else:
                error_msg = result.get('errMsg', 'Unknown error')
                logger.error("Failed to set battery mode: code=%s, msg=%s", err_code, error_msg)
                return False
                
        except Exception as e:
            logger.error("Exception setting battery mode: %s", e)
            return False
