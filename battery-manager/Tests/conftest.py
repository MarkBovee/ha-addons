"""Shared pytest fixtures for battery-manager tests."""

import pytest


@pytest.fixture(autouse=True)
def _isolated_decision_trace(tmp_path, monkeypatch):
    """Keep decision-trace output out of /data while tests run."""
    monkeypatch.setenv("DECISION_TRACE_PATH", str(tmp_path / "decision_trace.jsonl"))
