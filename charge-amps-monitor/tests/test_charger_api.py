import os
import sys
from datetime import datetime, timedelta, timezone

import requests

addon_root = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, addon_root)

for module_name in ["app", "app.charger_api", "app.main"]:
    sys.modules.pop(module_name, None)

from app.charger_api import ChargerApi
from app.main import publish_safe_charger_state_mqtt


class _FakeResponse:
    def __init__(self, ok=True, status_code=200, payload=None, text=""):
        self.ok = ok
        self.status_code = status_code
        self._payload = {} if payload is None else payload
        self.text = text

    def json(self):
        return self._payload


class _FakeSession:
    def __init__(self):
        self.headers = {}
        self.last_post = None
        self.last_get = None
        self.last_put = None
        self.last_delete = None
        self.login_calls = 0

    def post(self, url, headers=None, json=None, timeout=None):
        self.last_post = {
            "url": url,
            "headers": headers,
            "json": json,
            "timeout": timeout,
        }
        if url.endswith("/api/auth/login"):
            self.login_calls += 1
            return _FakeResponse(
                payload={
                    "token": "aaa.eyJleHAiOjE3NzQ0NTg5ODR9.bbb",
                    "user": {"id": "user-123"},
                }
            )
        return _FakeResponse(
            payload=[
                {
                    "id": "020100004457L",
                    "name": "Mark",
                    "chargePointStatus": "Online",
                    "connectors": [{"connectorId": 1, "isCharging": False}],
                }
            ]
        )

    def get(self, url, headers=None, timeout=None):
        self.last_get = {
            "url": url,
            "headers": headers,
            "timeout": timeout,
        }
        return _FakeResponse(payload=[])

    def put(self, url, headers=None, json=None, timeout=None):
        self.last_put = {
            "url": url,
            "headers": headers,
            "json": json,
            "timeout": timeout,
        }
        return _FakeResponse(payload={})

    def delete(self, url, headers=None, timeout=None):
        self.last_delete = {
            "url": url,
            "headers": headers,
            "timeout": timeout,
        }
        return _FakeResponse(payload={})


class _FakeMqttClient:
    def __init__(self):
        self.binary = []
        self.sensors = []

    def publish_binary_sensor(self, config):
        self.binary.append((config.object_id, config.state))

    def publish_sensor(self, config):
        self.sensors.append((config.object_id, config.state))


def test_authenticate_trims_config_and_matches_browser_login_headers():
    api = ChargerApi(
        " user@example.com ",
        " secret-pass \n",
        " my.charge.space/ ",
        " https://my.charge.space/ ",
    )
    fake_session = _FakeSession()
    fake_session.headers.update(api._session.headers)
    api._session = fake_session

    assert api.authenticate() is True

    assert fake_session.last_post["url"] == "https://my.charge.space/api/auth/login"
    assert fake_session.last_post["json"] == {
        "email": "user@example.com",
        "password": "secret-pass",
        "hostName": "my.charge.space",
    }
    assert fake_session.last_post["headers"]["Origin"] == "https://my.charge.space"
    assert fake_session.last_post["headers"]["Referer"] == "https://my.charge.space/userapp/login"


def test_publish_safe_charger_state_mqtt_zeros_live_measurements():
    mqtt_client = _FakeMqttClient()

    publish_safe_charger_state_mqtt(mqtt_client, status="auth_error", error_code="api_403")

    assert ("charging", "OFF") in mqtt_client.binary
    assert ("online", "OFF") in mqtt_client.binary
    assert ("connector_enabled", "OFF") in mqtt_client.binary
    assert ("current_power", "0") in mqtt_client.sensors
    assert ("power_kw", "0") in mqtt_client.sensors
    assert ("voltage", "0") in mqtt_client.sensors
    assert ("current", "0") in mqtt_client.sensors
    assert ("status", "auth_error") in mqtt_client.sensors
    assert ("error_code", "api_403") in mqtt_client.sensors


def test_get_charge_points_uses_browser_headers_and_expand_query():
    api = ChargerApi(
        "user@example.com",
        "secret-pass",
        "my.charge.space",
        "https://my.charge.space",
    )
    fake_session = _FakeSession()
    fake_session.headers.update(api._session.headers)
    api._session = fake_session
    api._auth_token = "token-123"
    api._token_expiration = api._token_expiration.replace(year=2099)

    charge_points = api.get_charge_points()

    assert charge_points is not None
    assert len(charge_points) == 1
    assert fake_session.last_post["url"] == (
        "https://my.charge.space/api/users/chargepoints/owned?expand=ocppConfig,topChargingLimitation"
    )
    assert fake_session.last_post["json"] == []
    assert fake_session.last_post["headers"]["Authorization"] == "Bearer token-123"
    assert fake_session.last_post["headers"]["Origin"] == "https://my.charge.space"
    assert fake_session.last_post["headers"]["Referer"] == "https://my.charge.space/userapp/dashboard"
    assert fake_session.last_post["headers"]["User-Agent"] == "Mozilla/5.0"


def test_authentication_token_without_expiry_is_reused():
    api = ChargerApi("user@example.com", "secret-pass")
    fake_session = _FakeSession()

    original_post = fake_session.post

    def post_without_expiry(url, headers=None, json=None, timeout=None):
        response = original_post(url, headers=headers, json=json, timeout=timeout)
        if url.endswith("/api/auth/login"):
            response._payload["token"] = "opaque-token"
        return response

    fake_session.post = post_without_expiry
    api._session = fake_session

    assert api.authenticate() is True
    assert api._token_expiration.year == 9999
    assert api.get_charge_points() is not None
    assert fake_session.login_calls == 1


def test_token_refresh_buffer_and_failed_reauthentication_are_deterministic():
    api = ChargerApi("user@example.com", "secret-pass")
    fake_session = _FakeSession()
    api._session = fake_session
    api._auth_token = "cached-token"
    api._token_expiration = datetime.now(timezone.utc) + timedelta(minutes=10)

    assert api._ensure_authenticated() is True
    assert fake_session.login_calls == 0

    api._token_expiration = datetime.now(timezone.utc) + timedelta(minutes=4)
    assert api._ensure_authenticated() is True
    assert fake_session.login_calls == 1

    class _AuthFailureSession(_FakeSession):
        def post(self, url, headers=None, json=None, timeout=None):
            self.last_post = {"url": url, "headers": headers, "json": json, "timeout": timeout}
            if url.endswith("/api/auth/login"):
                return _FakeResponse(ok=False, status_code=403, text="forbidden")
            return _FakeResponse(payload=[])

    api._session = _AuthFailureSession()
    api._auth_token = None
    assert api._ensure_authenticated() is False
    assert api.last_error.classification == "authentication_error"


def test_schedule_operations_keep_verified_paths_and_payloads():
    api = ChargerApi("user@example.com", "secret-pass")
    fake_session = _FakeSession()
    api._session = fake_session
    api._auth_token = "token-123"
    api._token_expiration = api._token_expiration.replace(year=2099)

    assert api.get_schedules("charger-1") == []
    assert api.upsert_schedule(
        charge_point_id="charger-1",
        connector_id=1,
        start_of_schedule="2026-09-07T00:00:00Z",
        schedule_periods=[{"from": 0, "to": 900}],
        max_current=12,
        timezone_name="Europe/Amsterdam",
    ) == {}
    assert api.delete_schedule("charger-1", 1) is True

    assert fake_session.last_get["url"].endswith(
        "/api/smartChargingSchedules/chargepoint/charger-1"
    )
    assert fake_session.last_put["url"].endswith("/api/smartChargingSchedules")
    assert fake_session.last_put["json"]["schedulePeriods"] == [
        {"from": 0, "to": 900, "maxCurrent": 12.0}
    ]
    assert fake_session.last_delete["url"].endswith(
        "/api/smartChargingSchedules/charger-1/1"
    )


def test_transient_read_retries_once_but_schedule_write_does_not():
    api = ChargerApi("user@example.com", "secret-pass", read_retries=1)
    calls = []

    class _RetrySession(_FakeSession):
        def request(self, method, url, headers=None, timeout=None, **kwargs):
            calls.append((method, url))
            if method == "GET" and len(calls) == 1:
                return _FakeResponse(ok=False, status_code=503)
            if method == "PUT":
                return _FakeResponse(ok=False, status_code=503)
            return _FakeResponse(payload=[])

    api._session = _RetrySession()
    api._auth_token = "token-123"
    api._token_expiration = api._token_expiration.replace(year=2099)

    assert api.get_schedules("charger-1") == []
    assert [method for method, _ in calls] == ["GET", "GET"]
    assert api.upsert_schedule(
        charge_point_id="charger-1",
        connector_id=1,
        start_of_schedule="2026-09-07T00:00:00Z",
        schedule_periods=[],
        max_current=12,
        timezone_name="Europe/Amsterdam",
    ) is None
    assert [method for method, _ in calls] == ["GET", "GET", "PUT"]


def test_request_exception_is_classified_without_retrying_mutation():
    api = ChargerApi("user@example.com", "secret-pass")

    class _FailingSession(_FakeSession):
        def put(self, url, headers=None, json=None, timeout=None):
            raise requests.RequestException("broken connection")

    api._session = _FailingSession()
    api._auth_token = "token-123"
    api._token_expiration = api._token_expiration.replace(year=2099)

    assert api.upsert_schedule(
        charge_point_id="charger-1",
        connector_id=1,
        start_of_schedule="2026-09-07T00:00:00Z",
        schedule_periods=[],
        max_current=12,
        timezone_name="Europe/Amsterdam",
    ) is None
    assert api.last_error.classification == "provider_error"
