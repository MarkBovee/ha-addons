"""Charge Amps API client for EV charger monitoring."""

from __future__ import annotations

import base64
import json
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import requests

from .models import ChargePoint

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_SECONDS = 30
DEFAULT_READ_RETRIES = 1
TOKEN_REFRESH_BUFFER = timedelta(minutes=5)


class ChargerApiError(Exception):
    """Base error for classified Charge Amps provider failures."""

    classification = "provider_error"

    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code


class AuthenticationError(ChargerApiError):
    """Authentication or authorization failed."""

    classification = "authentication_error"


class ProviderTimeoutError(ChargerApiError):
    """A provider request exceeded its timeout."""

    classification = "timeout"


class TransientProviderError(ChargerApiError):
    """A provider failure may succeed after bounded retry/backoff."""

    classification = "transient_provider_error"


class PermanentProviderError(ChargerApiError):
    """A provider rejected a request without a safe retry."""

    classification = "provider_error"


class MalformedResponseError(ChargerApiError):
    """The provider response cannot be parsed or validated."""

    classification = "malformed_response"


class UnsupportedOperationError(ChargerApiError):
    """The requested provider operation is not verified or supported."""

    classification = "unsupported_operation"


class ConstraintError(ChargerApiError):
    """A requested value violates a verified provider constraint."""

    classification = "constraint_error"


class ChargerApi:
    """Client for interacting with the Charge Amps API.

    Public methods retain the add-on's existing ``None``/``False`` failure
    contract. ``last_error`` exposes the classified failure for adapters and
    diagnostics without forcing a breaking runtime migration.
    """

    def __init__(
        self,
        email: str,
        password: str,
        host_name: str = "my.charge.space",
        base_url: str = "https://my.charge.space",
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        read_retries: int = DEFAULT_READ_RETRIES,
    ):
        self.email = (email or "").strip()
        self.password = (password or "").strip()
        self.base_url = self._normalize_base_url(base_url)
        self.host_name = self._normalize_host_name(host_name, self.base_url)
        self.timeout_seconds = timeout_seconds
        self.read_retries = max(0, read_retries)
        self._auth_token: Optional[str] = None
        self._user_id: Optional[str] = None
        self._token_expiration: datetime = datetime.min.replace(tzinfo=timezone.utc)
        self._session = requests.Session()
        self._session.headers.update({
            "Content-Type": "application/json",
            "Accept": "application/json",
        })
        self._last_error: Optional[ChargerApiError] = None

    @property
    def last_error(self) -> Optional[ChargerApiError]:
        """Return the last classified provider failure, if any."""
        return self._last_error

    def _browser_headers(
        self,
        referer_path: str,
        include_auth: bool = False,
        accept: str = "*/*",
    ) -> Dict[str, str]:
        headers = {
            "Accept": accept,
            "Origin": self.base_url,
            "Referer": f"{self.base_url}{referer_path}",
            "User-Agent": "Mozilla/5.0",
        }
        if include_auth:
            headers.update(self._auth_headers())
        return headers

    @staticmethod
    def _normalize_base_url(base_url: str) -> str:
        normalized = (base_url or "https://my.charge.space").strip().rstrip("/")
        return normalized or "https://my.charge.space"

    @staticmethod
    def _normalize_host_name(host_name: str, base_url: str) -> str:
        normalized = (host_name or "").strip().strip("/")
        if normalized:
            return normalized
        parsed = urlparse(base_url)
        return parsed.hostname or "my.charge.space"

    def _auth_headers(self) -> Dict[str, str]:
        if not self._ensure_authenticated():
            raise AuthenticationError("Authentication required")
        return {"Authorization": f"Bearer {self._auth_token}"}

    def authenticate(self) -> bool:
        """Authenticate and cache the provider JWT until it needs refresh."""
        try:
            self._auth_token = None
            self._user_id = None
            self._token_expiration = datetime.min.replace(tzinfo=timezone.utc)
            response = self._session.post(
                f"{self.base_url}/api/auth/login",
                headers=self._browser_headers("/userapp/login"),
                json={
                    "email": self.email,
                    "password": self.password,
                    "hostName": self.host_name,
                },
                timeout=self.timeout_seconds,
            )
            if not response.ok:
                raise AuthenticationError(
                    f"Authentication failed with status {response.status_code}",
                    response.status_code,
                )

            try:
                login_response = response.json()
            except (TypeError, ValueError) as exc:
                raise MalformedResponseError("Authentication response was not JSON") from exc

            token = login_response.get("token") if isinstance(login_response, dict) else None
            if not token:
                raise AuthenticationError("Authentication response did not contain a token")

            self._auth_token = token
            user = login_response.get("user") or {}
            self._user_id = user.get("id")
            self._token_expiration = self._parse_token_expiration(token)
            logger.info(
                "Authentication successful; token expiry=%s user_id=%s",
                self._token_expiration.isoformat(),
                self._user_id,
            )
            self._last_error = None
            return True
        except requests.Timeout as exc:
            error = ProviderTimeoutError("Authentication request timed out")
        except requests.RequestException as exc:
            error = AuthenticationError(f"Authentication request failed: {exc}")
        except ChargerApiError as exc:
            error = exc
        except Exception as exc:
            error = AuthenticationError(f"Authentication failed: {exc}")

        self._last_error = error
        self._auth_token = None
        logger.error("%s: %s", error.classification, error)
        return False

    @staticmethod
    def _parse_token_expiration(token: str) -> datetime:
        token_parts = token.split(".")
        if len(token_parts) != 3:
            logger.warning("JWT has no parseable expiry; retaining token until provider rejection")
            return datetime.max.replace(tzinfo=timezone.utc)
        payload = ChargerApi._decode_jwt_payload(token_parts[1])
        try:
            return datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
        except (KeyError, TypeError, ValueError, OverflowError):
            logger.warning("JWT has no parseable expiry; retaining token until provider rejection")
            return datetime.max.replace(tzinfo=timezone.utc)

    def _ensure_authenticated(self) -> bool:
        """Ensure cached token is usable without needless re-authentication."""
        if self._auth_token:
            refresh_at = self._token_expiration - TOKEN_REFRESH_BUFFER
            if datetime.now(timezone.utc) < refresh_at:
                return True
        logger.info("Token expired or missing, re-authenticating")
        return self.authenticate()

    def _request(
        self,
        method: str,
        path: str,
        *,
        headers: Dict[str, str],
        retryable_read: bool = False,
        **kwargs: Any,
    ) -> requests.Response:
        attempts = 1 + (self.read_retries if retryable_read else 0)
        for attempt in range(attempts):
            try:
                request = getattr(self._session, "request", None)
                if request:
                    response = request(
                        method,
                        f"{self.base_url}{path}",
                        headers=headers,
                        timeout=self.timeout_seconds,
                        **kwargs,
                    )
                else:
                    response = getattr(self._session, method.lower())(
                        f"{self.base_url}{path}",
                        headers=headers,
                        timeout=self.timeout_seconds,
                        **kwargs,
                    )
                if response.ok:
                    self._last_error = None
                    return response
                error = self._error_for_response(response)
                if isinstance(error, AuthenticationError):
                    self._auth_token = None
                if isinstance(error, TransientProviderError) and attempt + 1 < attempts:
                    time.sleep(0.25 * (2**attempt))
                    continue
                raise error
            except requests.Timeout as exc:
                error = ProviderTimeoutError(f"{method} {path} timed out")
                if attempt + 1 < attempts:
                    time.sleep(0.25 * (2**attempt))
                    continue
                raise error from exc
            except requests.ConnectionError as exc:
                error = TransientProviderError(f"{method} {path} connection failed")
                if attempt + 1 < attempts:
                    time.sleep(0.25 * (2**attempt))
                    continue
                raise error from exc
            except requests.RequestException as exc:
                raise PermanentProviderError(f"{method} {path} request failed: {exc}") from exc
        raise TransientProviderError(f"{method} {path} failed after retries")

    @staticmethod
    def _error_for_response(response: requests.Response) -> ChargerApiError:
        status = response.status_code
        if status in (401, 403):
            return AuthenticationError(f"Provider authorization failed ({status})", status)
        if status in (408, 429) or status >= 500:
            return TransientProviderError(f"Provider returned transient status {status}", status)
        return PermanentProviderError(f"Provider returned status {status}", status)

    @staticmethod
    def _json_response(response: requests.Response) -> Any:
        try:
            return response.json()
        except (TypeError, ValueError) as exc:
            raise MalformedResponseError("Provider response was not valid JSON") from exc

    def get_charge_points(self) -> Optional[List[ChargePoint]]:
        """Get owned charge points using a bounded retry for transient reads."""
        try:
            response = self._request(
                "POST",
                "/api/users/chargepoints/owned?expand=ocppConfig,topChargingLimitation",
                headers=self._browser_headers("/userapp/dashboard", include_auth=True),
                json=[],
                retryable_read=True,
            )
            payload = self._json_response(response)
            if not isinstance(payload, list):
                raise MalformedResponseError("Charge point response was not a list")
            charge_points = [ChargePoint.from_dict(item) for item in payload]
            logger.info("Successfully retrieved %d charge point(s)", len(charge_points))
            return charge_points
        except ChargerApiError as exc:
            self._last_error = exc
            logger.error("Failed to get charge points (%s): %s", exc.classification, exc)
            return None

    def get_schedules(self, charge_point_id: str) -> Optional[List[Dict[str, Any]]]:
        """Fetch smart charging schedules with a bounded retry for reads."""
        try:
            response = self._request(
                "GET",
                f"/api/smartChargingSchedules/chargepoint/{charge_point_id}",
                headers=self._browser_headers("/userapp/dashboard", include_auth=True),
                retryable_read=True,
            )
            payload = self._json_response(response)
            if not isinstance(payload, list):
                raise MalformedResponseError("Schedule response was not a list")
            return payload
        except ChargerApiError as exc:
            self._last_error = exc
            logger.error("Failed to fetch schedules (%s): %s", exc.classification, exc)
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
        """Create or update a smart charging schedule without blind retries."""
        periods_with_current = [
            {
                "from": period["from"],
                "to": period["to"],
                "maxCurrent": float(max_current),
            }
            for period in schedule_periods
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
            response = self._request(
                "PUT",
                "/api/smartChargingSchedules",
                headers=self._browser_headers("/userapp/dashboard", include_auth=True),
                json=payload,
            )
            result = self._json_response(response)
            if not isinstance(result, dict):
                raise MalformedResponseError("Schedule upsert response was not an object")
            logger.info("Smart charging schedule upserted: %d periods", len(periods_with_current))
            return result
        except ChargerApiError as exc:
            self._last_error = exc
            logger.error("Failed to upsert schedule (%s): %s", exc.classification, exc)
            return None

    def delete_schedule(self, charge_point_id: str, connector_id: int) -> bool:
        """Delete the automation schedule without blind retries."""
        try:
            self._request(
                "DELETE",
                f"/api/smartChargingSchedules/{charge_point_id}/{connector_id}",
                headers=self._browser_headers("/userapp/dashboard", include_auth=True),
            )
            logger.info("Deleted smart charging schedule for connector %s", connector_id)
            return True
        except ChargerApiError as exc:
            self._last_error = exc
            logger.error("Failed to delete schedule (%s): %s", exc.classification, exc)
            return False

    @staticmethod
    def _decode_jwt_payload(base64_payload: str) -> Optional[dict]:
        """Decode a JWT payload (base64url encoded)."""
        try:
            base64_str = base64_payload.replace("-", "+").replace("_", "/")
            padding = len(base64_str) % 4
            if padding:
                base64_str += "=" * (4 - padding)
            return json.loads(base64.b64decode(base64_str).decode("utf-8"))
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            logger.warning("Failed to decode JWT payload: %s", exc)
            return None
