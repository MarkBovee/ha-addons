"""API client for Charge Amps."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

import aiohttp

from .const import (
    API_AUTH_ENDPOINT,
    API_CHARGE_POINTS_ENDPOINT,
    CHARGE_POINT_STATUS_MAP,
    DEFAULT_BASE_URL,
    OCPP_STATUS_MAP,
)

_LOGGER = logging.getLogger(__name__)


@dataclass
class Connector:
    """Represents a charging connector."""

    connector_id: int
    is_charging: bool = False
    total_consumption_kwh: float = 0.0
    current1: float = 0.0
    current2: float = 0.0
    current3: float = 0.0
    voltage1: float = 0.0
    voltage2: float = 0.0
    voltage3: float = 0.0
    ocpp_status: int = 0

    @property
    def current_power_w(self) -> float:
        """Calculate current power in watts (3-phase)."""
        return (
            self.voltage1 * self.current1
            + self.voltage2 * self.current2
            + self.voltage3 * self.current3
        )

    @property
    def current_power_kw(self) -> float:
        """Calculate current power in kilowatts."""
        return self.current_power_w / 1000.0

    @property
    def ocpp_status_name(self) -> str:
        """Get human-readable OCPP status."""
        return OCPP_STATUS_MAP.get(self.ocpp_status, "Unknown")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Connector:
        """Create Connector from API response dict."""
        return cls(
            connector_id=data.get("connectorId", 0),
            is_charging=data.get("isCharging", False),
            total_consumption_kwh=data.get("totalConsumptionKwh", 0.0),
            current1=data.get("current1", 0.0),
            current2=data.get("current2", 0.0),
            current3=data.get("current3", 0.0),
            voltage1=data.get("voltage1", 0.0),
            voltage2=data.get("voltage2", 0.0),
            voltage3=data.get("voltage3", 0.0),
            ocpp_status=data.get("ocppStatus", 0),
        )


@dataclass
class ChargePoint:
    """Represents a Charge Amps charge point."""

    id: str
    name: str
    serial_number: str
    product_name: str
    charge_point_status: int = 0
    connectors: list[Connector] = field(default_factory=list)

    @property
    def status_name(self) -> str:
        """Get human-readable charge point status."""
        return CHARGE_POINT_STATUS_MAP.get(self.charge_point_status, "Unknown")

    @property
    def is_online(self) -> bool:
        """Check if charge point is online."""
        return self.charge_point_status == 1

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ChargePoint:
        """Create ChargePoint from API response dict."""
        connectors = [
            Connector.from_dict(c) for c in data.get("connectors", [])
        ]
        return cls(
            id=data.get("id", ""),
            name=data.get("name", "Unknown"),
            serial_number=data.get("serialNumber", ""),
            product_name=data.get("productName", ""),
            charge_point_status=data.get("chargePointStatus", 0),
            connectors=connectors,
        )


class ChargeAmpsApiError(Exception):
    """Base exception for Charge Amps API errors."""


class ChargeAmpsAuthError(ChargeAmpsApiError):
    """Authentication error."""


class ChargeAmpsConnectionError(ChargeAmpsApiError):
    """Connection error."""


class ChargeAmpsApi:
    """Async API client for Charge Amps."""

    def __init__(
        self,
        email: str,
        password: str,
        base_url: str = DEFAULT_BASE_URL,
        session: aiohttp.ClientSession | None = None,
    ) -> None:
        """Initialize the API client."""
        self._email = email
        self._password = password
        self._base_url = base_url.rstrip("/")
        self._session = session
        self._own_session = session is None
        self._token: str | None = None
        self._token_expiry: datetime | None = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create an aiohttp session."""
        if self._session is None:
            self._session = aiohttp.ClientSession()
            self._own_session = True
        return self._session

    async def close(self) -> None:
        """Close the session if we own it."""
        if self._own_session and self._session:
            await self._session.close()
            self._session = None

    async def authenticate(self) -> bool:
        """Authenticate with the Charge Amps API."""
        session = await self._get_session()
        url = f"{self._base_url}{API_AUTH_ENDPOINT}"

        try:
            async with session.post(
                url,
                json={"email": self._email, "password": self._password},
                headers={"Content-Type": "application/json"},
            ) as response:
                if response.status == 401:
                    raise ChargeAmpsAuthError("Invalid email or password")
                if response.status != 200:
                    raise ChargeAmpsConnectionError(
                        f"Authentication failed with status {response.status}"
                    )

                data = await response.json()
                self._token = data.get("token")
                expires_in = data.get("expiresIn", 3600)
                # Set expiry with 5-minute buffer
                self._token_expiry = datetime.now() + timedelta(
                    seconds=expires_in - 300
                )
                _LOGGER.debug("Successfully authenticated with Charge Amps API")
                return True

        except aiohttp.ClientError as err:
            raise ChargeAmpsConnectionError(f"Connection error: {err}") from err

    async def _ensure_authenticated(self) -> None:
        """Ensure we have a valid token."""
        if (
            self._token is None
            or self._token_expiry is None
            or datetime.now() >= self._token_expiry
        ):
            await self.authenticate()

    def _get_auth_headers(self) -> dict[str, str]:
        """Get headers with authorization token."""
        return {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
        }

    async def get_charge_points(self) -> list[ChargePoint]:
        """Get all charge points for the authenticated user."""
        await self._ensure_authenticated()
        session = await self._get_session()
        url = f"{self._base_url}{API_CHARGE_POINTS_ENDPOINT}"

        try:
            async with session.post(
                url,
                params={"expand": "ocppConfig"},
                headers=self._get_auth_headers(),
                json={},
            ) as response:
                if response.status == 401:
                    # Token might be invalid, try re-auth
                    self._token = None
                    await self._ensure_authenticated()
                    async with session.post(
                        url,
                        params={"expand": "ocppConfig"},
                        headers=self._get_auth_headers(),
                        json={},
                    ) as retry_response:
                        if retry_response.status != 200:
                            raise ChargeAmpsConnectionError(
                                f"Failed to get charge points: {retry_response.status}"
                            )
                        data = await retry_response.json()
                elif response.status != 200:
                    raise ChargeAmpsConnectionError(
                        f"Failed to get charge points: {response.status}"
                    )
                else:
                    data = await response.json()

                charge_points = [ChargePoint.from_dict(cp) for cp in data]
                _LOGGER.debug("Retrieved %d charge points", len(charge_points))
                return charge_points

        except aiohttp.ClientError as err:
            raise ChargeAmpsConnectionError(f"Connection error: {err}") from err

    async def validate_credentials(self) -> bool:
        """Validate the credentials by attempting to authenticate."""
        try:
            await self.authenticate()
            return True
        except ChargeAmpsApiError:
            return False
