"""Append-only decision trace: one JSON line per schedule generation."""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from dateutil.parser import isoparse

logger = logging.getLogger(__name__)

DEFAULT_TRACE_PATH = "/data/decision_trace.jsonl"
MAX_TRACE_BYTES = 20 * 1024 * 1024
MAX_TRACE_AGE = timedelta(days=14)
# Home Assistant drops state attributes above 16 KiB; stay well below.
MAX_ATTRIBUTE_BYTES = 12 * 1024


def get_trace_path(config: Dict[str, Any]) -> str:
    """Return the trace file path (env DECISION_TRACE_PATH overrides the default)."""
    return os.getenv("DECISION_TRACE_PATH") or config.get("decision_trace", {}).get("path") or DEFAULT_TRACE_PATH


def _first_record_time(path: str) -> Optional[datetime]:
    try:
        with open(path, "r", encoding="utf-8") as handle:
            first = handle.readline()
        stamp = json.loads(first).get("timestamp_utc")
        return isoparse(stamp) if stamp else None
    except (OSError, ValueError, TypeError):
        return None


def _rotate_if_needed(path: str, now: datetime) -> None:
    """Move the file to ``<path>.1`` once it is too big or too old (one backup kept)."""
    try:
        if not os.path.exists(path):
            return
        too_big = os.path.getsize(path) >= MAX_TRACE_BYTES
        first = _first_record_time(path)
        too_old = first is not None and now - first >= MAX_TRACE_AGE
        if too_big or too_old:
            os.replace(path, path + ".1")
            logger.info("🗂️ Decision trace rotated (%s)", "size" if too_big else "age")
    except OSError as exc:
        logger.warning("⚠️ Decision trace rotation failed: %s", exc)


def write_trace(path: str, record: Dict[str, Any], now: Optional[datetime] = None) -> bool:
    """Append ``record`` as one JSON line. Never raises; returns success."""
    now = now or datetime.now(timezone.utc)
    try:
        directory = os.path.dirname(path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        _rotate_if_needed(path, now)
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False, default=str, separators=(",", ":")) + "\n")
        return True
    except OSError as exc:
        logger.warning("⚠️ Decision trace not written to %s: %s", path, exc)
        return False


def summarize(record: Dict[str, Any]) -> str:
    """Return the one-line summary used for the sensor state and the INFO log."""
    final = record.get("final", {})
    charge = final.get("charge", [])
    discharge = final.get("discharge", [])
    sells = [p for p in discharge if p.get("window_type") == "discharge"]
    filtered = [w for w in record.get("discharge_windows", []) if w.get("decision") in ("dropped", "truncated")]
    soc = record.get("soc")
    solar = record.get("solar_aware") or {}
    pre = record.get("precharge") or {}
    parts = [
        f"SoC {soc:.0f}%" if isinstance(soc, (int, float)) else "SoC ?",
        f"import {record.get('import_price')} export {record.get('export_price')}",
        f"sell {len(sells)} ({sum(int(p.get('duration', 0)) for p in sells)}m)",
        f"charge {len(charge)} ({', '.join(str(p.get('power')) + 'W' for p in charge[:3])})" if charge else "charge 0",
    ]
    if filtered:
        parts.append(f"filtered {len(filtered)}")
    if solar.get("applied"):
        parts.append(f"grid target {solar.get('grid_target_kwh')}kWh")
    if pre.get("decision") and pre.get("decision") != "none":
        parts.append(f"precharge {pre['decision']}")
    skipped = [g for g in record.get("margin_gate", []) if not g.get("allowed")]
    if skipped:
        parts.append(f"margin-skip {len(skipped)}")
    return "🧭 Decision | " + " | ".join(parts)


def fit_attributes(record: Dict[str, Any]) -> Dict[str, Any]:
    """Return ``record`` trimmed so the JSON stays below the HA attribute limit."""
    attributes = dict(record)
    if len(json.dumps(attributes, default=str)) <= MAX_ATTRIBUTE_BYTES:
        return attributes
    for key in ("discharge_windows_before", "power_changes", "margin_gate", "charge_locks", "ranges"):
        attributes.pop(key, None)
        if len(json.dumps(attributes, default=str)) <= MAX_ATTRIBUTE_BYTES:
            attributes["truncated"] = True
            return attributes
    keep = ("timestamp_utc", "timestamp_local", "soc", "final")
    return {**{k: attributes[k] for k in keep if k in attributes}, "truncated": True}
