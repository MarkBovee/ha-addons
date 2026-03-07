"""Tests for schedule validation normalization rules."""

import os
import sys
import types

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Allow importing app.main without requiring pycryptodome in test env.
crypto_module = types.ModuleType("Crypto")
cipher_module = types.ModuleType("Crypto.Cipher")
cipher_module.AES = object
sys.modules.setdefault("Crypto", crypto_module)
sys.modules.setdefault("Crypto.Cipher", cipher_module)

from app.main import validate_schedule


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
