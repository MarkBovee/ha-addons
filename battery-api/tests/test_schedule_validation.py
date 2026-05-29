"""Tests for schedule validation normalization rules."""

import json
import os
import sys
import types
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Allow importing app.main without requiring pycryptodome in test env.
crypto_module = types.ModuleType("Crypto")
cipher_module = types.ModuleType("Crypto.Cipher")
cipher_module.AES = object
sys.modules.setdefault("Crypto", crypto_module)
sys.modules.setdefault("Crypto.Cipher", cipher_module)

from app.main import BatteryApiAddon, validate_schedule
from app.main import load_config
from app.backends import ApiBatteryBackend, BackendContext, build_backend, ModbusEntityDiscovery, ModbusHaBatteryBackend
from app.models import BatteryChargeType, ChargingPeriod


def test_discharge_duration_clipped_at_end_of_day():
    payload = '{"discharge":[{"start":"22:00","power":2100,"duration":720}]}'

    validated = validate_schedule(payload)

    assert validated["charge"] == []
    assert len(validated["discharge"]) == 1
    assert validated["discharge"][0]["start"] == "22:00"
    assert validated["discharge"][0]["duration"] == 119


def test_full_day_duration_clipped_to_2359_limit():
    payload = '{"charge":[{"start":"00:00","power":3000,"duration":1440}]}'

    validated = validate_schedule(payload)

    assert len(validated["charge"]) == 1
    assert validated["charge"][0]["duration"] == 1439


def test_duration_kept_when_already_same_day():
    payload = '{"discharge":[{"start":"20:00","power":2500,"duration":120}]}'

    validated = validate_schedule(payload)

    assert validated["discharge"][0]["duration"] == 120


def test_schedule_accepts_up_to_seven_periods_per_direction():
    payload = json.dumps(
        {
            "charge": [
                {"start": f"0{i}:00", "power": 1000 + i * 100, "duration": 30}
                for i in range(7)
            ],
            "discharge": [
                {"start": f"1{i}:00", "power": 2000 + i * 100, "duration": 30}
                for i in range(7)
            ],
        }
    )

    validated = validate_schedule(payload)

    assert len(validated["charge"]) == 7
    assert len(validated["discharge"]) == 7


def test_load_config_allows_modbus_provider_without_api_credentials(tmp_path, monkeypatch):
    config_path = tmp_path / "options.json"
    config_path.write_text('{"provider":"modbus_ha","poll_interval_seconds":60}')
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("app.main.load_addon_config", lambda defaults, required_fields: {
        **defaults,
        "provider": "modbus_ha",
        "poll_interval_seconds": 60,
    })

    config = load_config()

    assert config["provider"] == "modbus_ha"
    assert config["modbus_inverter_power_w"] == 8000


def test_build_backend_uses_modbus_provider():
    context = BackendContext(
        config={"provider": "modbus_ha", "modbus_inverter_power_w": 8000, "modbus_entities": {}},
        status={},
        simulation_mode=True,
        battery_mode_setting="Self-consumption",
        schedule_json="{}",
        validated_schedule=None,
    )

    backend = build_backend(context)

    assert backend.provider_name == "modbus_ha"
    assert backend.get_capabilities()["provider"] == "modbus_ha"


def test_modbus_entity_discovery_prefers_known_live_defaults():
    class FakeHaApi:
        def get_states(self):
            return [
                {"entity_id": "sensor.saj_battery_energy_percent"},
                {"entity_id": "sensor.saj_battery_power"},
                {"entity_id": "sensor.saj_pv_power"},
                {"entity_id": "sensor.saj_total_grid_power"},
                {"entity_id": "sensor.saj_total_load_power"},
                {"entity_id": "number.saj_app_mode_input"},
                {"entity_id": "number.saj_export_limit_input"},
                {"entity_id": "number.saj_passive_charge_enable"},
                {"entity_id": "sensor.saj_charge_time_enable_bitmask"},
                {"entity_id": "sensor.saj_discharge_time_enable_bitmask"},
                {"entity_id": "number.saj_charge_time_enable_input"},
                {"entity_id": "number.saj_discharge_time_enable_input"},
                {"entity_id": "sensor.saj_charge_start_time"},
                {"entity_id": "sensor.saj_charge_end_time"},
                {"entity_id": "sensor.saj_charge_day_mask"},
                {"entity_id": "sensor.saj_charge_power_percent"},
                {"entity_id": "text.saj_charge1_start_time_time"},
                {"entity_id": "text.saj_charge1_end_time_time"},
                {"entity_id": "number.saj_charge1_day_mask_input"},
                {"entity_id": "number.saj_charge1_power_percent_input"},
            ]

    discovery = ModbusEntityDiscovery(FakeHaApi())

    resolved = discovery.resolve()

    assert resolved["soc"] == "sensor.saj_battery_energy_percent"
    assert resolved["app_mode_input"] == "number.saj_app_mode_input"
    assert resolved["export_limit"] == "number.saj_export_limit_input"
    assert resolved["passive_charge_enable"] == "number.saj_passive_charge_enable"
    assert resolved["charge1_power_percent_input"] == "number.saj_charge1_power_percent_input"


def test_modbus_capabilities_expose_passive_mode_when_mapped():
    context = BackendContext(
        config={"provider": "modbus_ha", "modbus_inverter_power_w": 8000, "modbus_entities": {}},
        status={},
        simulation_mode=False,
        battery_mode_setting="Self-consumption",
        schedule_json="{}",
        validated_schedule=None,
    )
    backend = ModbusHaBatteryBackend(context)
    backend.entities = {
        "app_mode_input": "number.saj_app_mode_input",
        "charge_time_enable_input": "number.saj_charge_time_enable_input",
        "discharge_time_enable_input": "number.saj_discharge_time_enable_input",
        "export_limit": "number.saj_export_limit_input",
        "passive_charge_enable": "number.saj_passive_charge_enable_input",
        "switch_passive_charge": "switch.saj_passive_charge_control",
        "switch_passive_discharge": "switch.saj_passive_discharge_control",
        "passive_grid_charge_power": "number.saj_passive_grid_charge_power_input",
    }

    capabilities = backend.get_capabilities()

    assert capabilities["export_limit"] is True
    assert capabilities["passive_mode"] is True
    assert capabilities["passive_mode_mapped"] is True
    assert "passive_mode" in capabilities["experimental_controls"]
    assert "passive_grid_charge_power" in capabilities["experimental_controls"]
    assert capabilities["unsupported_controls"] == ["pv_off"]


def test_modbus_set_mode_verifies_read_back():
    context = BackendContext(
        config={"provider": "modbus_ha", "modbus_inverter_power_w": 8000, "modbus_entities": {}},
        status={},
        simulation_mode=False,
        battery_mode_setting="Self-consumption",
        schedule_json="{}",
        validated_schedule=None,
    )
    backend = ModbusHaBatteryBackend(context)
    backend.entities = {
        "app_mode_input": "number.saj_app_mode_input",
        "app_mode": "sensor.saj_app_mode",
    }

    with patch.object(backend, "_set_number", return_value=True) as set_number:
        with patch.object(backend, "_wait_for_int_value", return_value=1) as wait_for_int:
            assert backend.set_mode("Time-of-use") is True

    set_number.assert_called_once_with("app_mode_input", 1)
    wait_for_int.assert_called_once_with("app_mode", 1, attempts=20, delay_seconds=1.0)
    assert context.battery_mode_setting == "Time-of-use"


def test_modbus_set_export_limit_verifies_read_back():
    context = BackendContext(
        config={"provider": "modbus_ha", "modbus_inverter_power_w": 8000, "modbus_entities": {}},
        status={},
        simulation_mode=False,
        battery_mode_setting="Self-consumption",
        schedule_json="{}",
        validated_schedule=None,
    )
    backend = ModbusHaBatteryBackend(context)
    backend.entities = {
        "export_limit": "number.saj_export_limit_input",
    }

    with patch.object(backend, "_call_service", return_value=True) as call_service:
        with patch.object(backend, "_wait_for_int_value", return_value=1100) as wait_for_int:
            assert backend.set_export_limit(9999) is True

    call_service.assert_called_once_with("number", "set_value", "number.saj_export_limit_input", 1100)
    wait_for_int.assert_called_once_with("export_limit", 1100)
    assert context.status["export_limit"] == 1100


def test_modbus_set_passive_mode_verifies_read_back():
    context = BackendContext(
        config={"provider": "modbus_ha", "modbus_inverter_power_w": 8000, "modbus_entities": {}},
        status={},
        simulation_mode=False,
        battery_mode_setting="Self-consumption",
        schedule_json="{}",
        validated_schedule=None,
    )
    backend = ModbusHaBatteryBackend(context)
    backend.entities = {
        "passive_charge_enable": "number.saj_passive_charge_enable_input",
        "switch_passive_charge": "switch.saj_passive_charge_control",
        "switch_passive_discharge": "switch.saj_passive_discharge_control",
    }

    with patch.object(backend, "_get_int", return_value=0):
        with patch.object(backend, "_call_service", return_value=True) as call_service:
            with patch.object(backend, "_wait_for_int_value", return_value=2) as wait_for_int:
                assert backend.set_passive_mode("Passive charge") is True

    call_service.assert_called_once_with("switch", "turn_on", "switch.saj_passive_charge_control", None)
    wait_for_int.assert_called_once_with("passive_charge_enable", 2, attempts=20, delay_seconds=1.0)
    assert context.status["passive_mode"] == "Passive charge"


def test_modbus_set_passive_mode_off_turns_off_active_switch():
    context = BackendContext(
        config={"provider": "modbus_ha", "modbus_inverter_power_w": 8000, "modbus_entities": {}},
        status={},
        simulation_mode=False,
        battery_mode_setting="Self-consumption",
        schedule_json="{}",
        validated_schedule=None,
    )
    backend = ModbusHaBatteryBackend(context)
    backend.entities = {
        "passive_charge_enable": "number.saj_passive_charge_enable_input",
        "switch_passive_charge": "switch.saj_passive_charge_control",
        "switch_passive_discharge": "switch.saj_passive_discharge_control",
    }

    with patch.object(backend, "_get_int", return_value=1):
        with patch.object(backend, "_call_service", return_value=True) as call_service:
            with patch.object(backend, "_wait_for_int_value", return_value=0) as wait_for_int:
                assert backend.set_passive_mode("Off") is True

    call_service.assert_called_once_with("switch", "turn_off", "switch.saj_passive_discharge_control", None)
    wait_for_int.assert_called_once_with("passive_charge_enable", 0, attempts=20, delay_seconds=1.0)
    assert context.status["passive_mode"] == "Off"


def test_publish_discovery_removes_or_publishes_optional_controls_by_capability():
    fake_backend = MagicMock()

    with patch("app.main.build_backend", return_value=fake_backend):
        addon = BatteryApiAddon(
            {"provider": "modbus_ha", "simulation_mode": True, "poll_interval_seconds": 60},
            None,
        )

    addon.mqtt = MagicMock()
    addon.mqtt.get_published_entities.return_value = []

    addon.status["provider_capabilities"] = {}
    addon._publish_discovery_configs()

    addon.mqtt.remove_entity.assert_any_call("number", "export_limit")
    addon.mqtt.remove_entity.assert_any_call("select", "passive_mode")

    addon.mqtt.reset_mock()
    addon.mqtt.get_published_entities.return_value = []

    addon.status["provider_capabilities"] = {"export_limit": True, "passive_mode": True}
    addon.status["export_limit"] = 300
    addon.status["passive_mode"] = "Passive discharge"
    addon._publish_discovery_configs()

    assert any(
        call.args[0].object_id == "export_limit"
        for call in addon.mqtt.publish_number.call_args_list
    )
    assert any(
        call.args[0].object_id == "passive_mode" and call.args[0].state == "Passive discharge"
        for call in addon.mqtt.publish_select.call_args_list
    )


def test_modbus_save_schedule_waits_for_delayed_read_back():
    context = BackendContext(
        config={"provider": "modbus_ha", "modbus_inverter_power_w": 8000, "modbus_entities": {}},
        status={},
        simulation_mode=False,
        battery_mode_setting="Self-consumption",
        schedule_json="{}",
        validated_schedule=None,
    )
    backend = ModbusHaBatteryBackend(context)

    expected_schedule = {
        "charge": [{"start": "11:15", "duration": 240, "power": 4880}],
        "discharge": [{"start": "20:00", "duration": 120, "power": 8000}],
    }
    stale_schedule = {
        "charge": [{"start": "11:00", "duration": 240, "power": 4880}],
        "discharge": [{"start": "20:00", "duration": 120, "power": 8000}],
    }

    with patch.object(backend, "_write_slots", return_value=None) as write_slots:
        with patch.object(backend, "_set_number", return_value=True) as set_number:
            with patch.object(backend, "set_mode", return_value=True) as set_mode:
                with patch.object(backend, "_read_schedule_from_ha", side_effect=[stale_schedule, expected_schedule]):
                    with patch("app.backends.time.sleep", return_value=None):
                        assert backend.save_schedule([], json.dumps(expected_schedule)) is True

    assert write_slots.call_count == 2
    assert set_number.call_count == 2
    set_mode.assert_called_once_with("Time-of-use")
    assert json.loads(context.status["current_schedule"]) == expected_schedule


def test_api_provider_rejects_schedule_above_cloud_slot_limits():
    context = BackendContext(
        config={
            "provider": "api",
            "saj_username": "user@example.com",
            "saj_password": "secret",
            "device_serial_number": "SERIAL",
            "plant_uid": "PLANT",
        },
        status={},
        simulation_mode=True,
        battery_mode_setting="Self-consumption",
        schedule_json="{}",
        validated_schedule=None,
    )
    backend = ApiBatteryBackend(context)
    periods = [
        ChargingPeriod(BatteryChargeType.CHARGE, f"0{i}:00", 30, 1000)
        for i in range(4)
    ]

    assert backend.save_schedule(periods, "{}") is False
    assert "max 3 charge and 6 discharge periods" in context.status["schedule_status"]


def test_wait_for_schedule_polls_until_match():
    context = BackendContext(
        config={"provider": "modbus_ha", "modbus_inverter_power_w": 8000, "modbus_entities": {}},
        status={},
        simulation_mode=False,
        battery_mode_setting="Self-consumption",
        schedule_json="{}",
        validated_schedule=None,
    )
    backend = ModbusHaBatteryBackend(context)

    expected_schedule = {
        "charge": [{"start": "11:15", "duration": 241, "power": 4800}],
        "discharge": [{"start": "20:00", "duration": 120, "power": 8000}],
    }
    stale_schedule = {
        "charge": [{"start": "11:00", "duration": 240, "power": 4800}],
        "discharge": [{"start": "20:00", "duration": 120, "power": 8000}],
    }

    with patch.object(backend, "_read_schedule_from_ha", side_effect=[stale_schedule, stale_schedule, expected_schedule]):
        with patch.object(backend, "_refresh_entities", return_value=None) as refresh_entities:
            with patch("app.backends.time.sleep", return_value=None):
                actual = backend._wait_for_schedule(expected_schedule, attempts=3, delay_seconds=0.1)

    assert actual == expected_schedule
    assert refresh_entities.call_count == 2
