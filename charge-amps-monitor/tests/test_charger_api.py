import os
import sys

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
        self._payload = payload or {}
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

    def post(self, url, headers=None, json=None, timeout=None):
        self.last_post = {
            "url": url,
            "headers": headers,
            "json": json,
            "timeout": timeout,
        }
        if url.endswith("/api/auth/login"):
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