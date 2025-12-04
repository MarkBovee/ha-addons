"""Charge Amps API client for EV charger monitoring."""

import base64
import json
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import requests

from .models import ChargePoint, Connector

logger = logging.getLogger(__name__)


class ChargerApi:
    """Client for interacting with the Charge Amps API."""
    
    def __init__(
        self,
        email: str,
        password: str,
        host_name: str = "my.charge.space",
        base_url: str = "https://my.charge.space"
    ):
        """Initialize the API client."""
        self.email = email
        self.password = password
        self.host_name = host_name
        self.base_url = base_url
        self._auth_token: Optional[str] = None
        self._user_id: Optional[str] = None
        self._token_expiration: datetime = datetime.min.replace(tzinfo=timezone.utc)
        self._session = requests.Session()
        self._session.headers.update({
            "Content-Type": "application/json",
            "Accept": "application/json"
        })

    def _auth_headers(self) -> Dict[str, str]:
        if not self._ensure_authenticated():
            raise RuntimeError("Authentication required")
        return {"Authorization": f"Bearer {self._auth_token}"}
    
    def authenticate(self) -> bool:
        """Authenticate with the Charge Amps API and retrieve an access token."""
        try:
            login_request = {
                "email": self.email,
                "password": self.password,
                "hostName": self.host_name
            }
            
            response = self._session.post(
                f"{self.base_url}/api/auth/login",
                json=login_request,
                timeout=30
            )
            
            if not response.ok:
                logger.error(f"Authentication failed with status code: {response.status_code}")
                return False
            
            login_response = response.json()
            
            if "token" not in login_response or not login_response["token"]:
                logger.error("Authentication response did not contain a token")
                return False
            
            self._auth_token = login_response["token"]
            if "user" in login_response and login_response["user"]:
                self._user_id = login_response["user"].get("id")
            
            # Parse JWT to get expiration
            token_parts = self._auth_token.split('.')
            if len(token_parts) == 3:
                try:
                    payload = self._decode_jwt_payload(token_parts[1])
                    if payload and "exp" in payload:
                        self._token_expiration = datetime.fromtimestamp(
                            payload["exp"], 
                            tz=timezone.utc
                        )
                        logger.info(
                            f"Authentication successful. Token expires at {self._token_expiration}. "
                            f"User ID: {self._user_id}"
                        )
                except Exception as ex:
                    logger.warning(f"Could not parse token expiration: {ex}")
            
            return True
            
        except Exception as ex:
            logger.error(f"Exception during authentication: {ex}", exc_info=True)
            return False
    
    def _ensure_authenticated(self) -> bool:
        """Ensure we have a valid authentication token, refreshing if necessary."""
        # Check if token is still valid (with 5 minute buffer)
        if self._auth_token:
            # Add 5 minute buffer to expiration time
            buffer_time = self._token_expiration - timedelta(minutes=5)
            if datetime.now(timezone.utc) < buffer_time:
                return True
        
        logger.info("Token expired or missing, re-authenticating...")
        return self.authenticate()
    
    def get_charge_points(self) -> Optional[List[ChargePoint]]:
        """Get the list of charge points for the authenticated user."""
        try:
            request_headers = self._auth_headers()
            response = self._session.post(
                f"{self.base_url}/api/users/chargepoints/owned?expand=ocppConfig",
                headers=request_headers,
                json=[],
                timeout=30
            )
            
            if not response.ok:
                logger.error(f"Failed to get charge points: {response.status_code}")
                return None
            
            charge_points_data = response.json()
            charge_points = [ChargePoint.from_dict(cp) for cp in charge_points_data]
            
            logger.info(f"Successfully retrieved {len(charge_points)} charge point(s)")
            return charge_points
            
        except Exception as ex:
            logger.error(f"Exception while getting charge points: {ex}", exc_info=True)
            return None

    def get_schedules(self, charge_point_id: str) -> Optional[List[Dict[str, Any]]]:
        """Fetch smart charging schedules for a charge point."""
        try:
            headers = self._auth_headers()
            response = self._session.get(
                f"{self.base_url}/api/smartChargingSchedules/chargepoint/{charge_point_id}",
                headers=headers,
                timeout=30,
            )
            if response.ok:
                return response.json()
            logger.error("Failed to fetch schedules (%s): %s", response.status_code, response.text[:200])
            return None
        except Exception as exc:
            logger.error("Exception fetching schedules: %s", exc, exc_info=True)
            return None

    def upsert_schedule(
        self,
        charge_point_id: str,
        connector_id: int,
        start_of_schedule: str,
        schedule_periods: List[Dict[str, Any]],
        max_current: float,
        timezone_name: str,
        schedule_id: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
        """Create or update a smart charging schedule with multiple periods.
        
        Args:
            charge_point_id: The charger ID
            connector_id: The connector number (usually 1)
            start_of_schedule: ISO timestamp for the start of the week (Sunday midnight UTC)
            schedule_periods: List of dicts with 'from' and 'to' as seconds from week start
            max_current: Maximum current in amps for all periods
            timezone_name: Timezone name (e.g., "Europe/Amsterdam")
            schedule_id: Optional existing schedule ID for updates
        """
        # Add maxCurrent to each period
        periods_with_current = [
            {
                "from": p["from"],
                "to": p["to"],
                "maxCurrent": float(max_current),
            }
            for p in schedule_periods
        ]
        
        payload = {
            "scheduleId": schedule_id,
            "chargePointId": charge_point_id,
            "connectorId": connector_id,
            "validFrom": None,
            "validTo": None,
            "defaultCurrent": 0,
            "schedulePeriods": periods_with_current,
            "isActive": True,
            "isSynced": True,
            "timeZone": timezone_name,
            "startOfSchedule": start_of_schedule,
        }

        try:
            headers = self._auth_headers()
            response = self._session.put(
                f"{self.base_url}/api/smartChargingSchedules",
                headers=headers,
                json=payload,
                timeout=30,
            )
            if response.ok:
                logger.info("Smart charging schedule upserted: %d periods", len(periods_with_current))
                return response.json()
            logger.error(
                "Failed to upsert schedule (%s): %s",
                response.status_code,
                response.text[:200],
            )
            return None
        except Exception as exc:
            logger.error("Exception writing schedule: %s", exc, exc_info=True)
            return None

    def delete_schedule(self, charge_point_id: str, connector_id: int) -> bool:
        """Delete the automation schedule for the connector."""
        try:
            headers = self._auth_headers()
            response = self._session.delete(
                f"{self.base_url}/api/smartChargingSchedules/{charge_point_id}/{connector_id}",
                headers=headers,
                timeout=30,
            )
            if response.ok:
                logger.info("Deleted smart charging schedule for connector %s", connector_id)
                return True
            logger.error(
                "Failed to delete schedule (%s): %s",
                response.status_code,
                response.text[:200],
            )
            return False
        except Exception as exc:
            logger.error("Exception deleting schedule: %s", exc, exc_info=True)
            return False
    
    @staticmethod
    def _decode_jwt_payload(base64_payload: str) -> Optional[dict]:
        """Decode a JWT payload (base64url encoded)."""
        try:
            # Convert base64url to base64
            base64_str = base64_payload.replace('-', '+').replace('_', '/')
            
            # Add padding if necessary
            padding = len(base64_str) % 4
            if padding:
                base64_str += '=' * (4 - padding)
            
            json_bytes = base64.b64decode(base64_str)
            json_str = json_bytes.decode('utf-8')
            
            return json.loads(json_str)
        except Exception as ex:
            logger.warning(f"Failed to decode JWT payload: {ex}")
            return None

