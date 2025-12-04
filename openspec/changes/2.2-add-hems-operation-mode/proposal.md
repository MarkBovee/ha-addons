# Proposal: Add HEMS Operation Mode to Charge Amps Monitor

**Version:** 2.2  
**Status:** ⏳ DRAFT - 0%  
**Created:** 2025-12-04  
**Completed:** TBD

## Why

The charge-amps-monitor add-on currently operates in a standalone fashion: it fetches electricity prices, calculates the cheapest charging windows, and pushes schedules to the Charge Amps charger autonomously. This works well for single-device optimization but becomes limiting when users want centralized energy management across multiple appliances (EV charger, water heater, battery storage, heat pump).

A future Home Energy Management System (HEMS) will coordinate all these devices to optimize whole-home energy consumption. The EV charger add-on needs to support being orchestrated by such a system rather than making independent scheduling decisions.

Additionally, the standalone mode needs improvement: currently it selects the top X cheapest slots regardless of absolute price. Users want a **price threshold** to avoid charging during expensive periods even if they're technically the "cheapest" available.

## What Changes

| Aspect | Before | After |
|--------|--------|-------|
| Operation mode | Always standalone (implicit) | Explicit `operation_mode`: `standalone` or `hems` |
| Price selection | Top X slots regardless of price | Standalone: Top X **unique price levels** below `price_threshold` |
| Price threshold | None | New `price_threshold` config (default 0.25 EUR/kWh) |
| Schedule source | Internal price analyzer only | Standalone: internal | HEMS: external via MQTT |
| MQTT role | Entity publishing only | Also listens for HEMS schedule commands |
| Telemetry | Basic charger status | Adds HEMS-relevant status (ready state, applied schedule source) |

## Benefits

1. **HEMS-ready architecture** – The add-on can be orchestrated by a central energy manager without code changes, enabling whole-home optimization.
2. **Smarter standalone charging** – Price threshold prevents charging during expensive periods; unique price selection maximizes charging during truly cheap windows.
3. **Seamless transition** – Users can start with standalone mode and later switch to HEMS when they deploy centralized management.
4. **Better observability** – New sensors expose schedule source, HEMS connection status, and applied schedule details.

## Dependencies

- Existing MQTT infrastructure (Mosquitto broker)
- Future HEMS system will publish to defined MQTT topics (this change defines the contract)
- `energy-prices` add-on (standalone mode) for price data

## Configuration Changes

| Config Key | Type | Default | Description |
|------------|------|---------|-------------|
| `operation_mode` | `list(standalone\|hems)` | `standalone` | Controls scheduling behavior |
| `price_threshold` | `float` | `0.25` | EUR/kWh - max price for charging (standalone only) |
| `top_x_charge_count` | `int` | `16` | **Modified**: Now selects top X unique price levels, not slots |

## HEMS MQTT Contract

### Subscribe Topics

| Topic | Payload | Description |
|-------|---------|-------------|
| `hems/charge-amps/{connector_id}/schedule/set` | JSON schedule | Apply new charging schedule |
| `hems/charge-amps/{connector_id}/schedule/clear` | Empty/null | Clear current schedule, stop charging |

### Schedule Payload Format

```json
{
  "source": "hems",
  "periods": [
    {"start": "2025-12-04T22:00:00+01:00", "end": "2025-12-04T23:00:00+01:00"},
    {"start": "2025-12-05T02:00:00+01:00", "end": "2025-12-05T06:00:00+01:00"}
  ],
  "max_current": 16,
  "expires_at": "2025-12-05T08:00:00+01:00"
}
```

### Publish Topics (Status)

| Topic | Payload | Description |
|-------|---------|-------------|
| `hems/charge-amps/{connector_id}/status` | JSON status | Current charger state and readiness |

### Status Payload Format

```json
{
  "state": "idle|charging|plugged_in|error",
  "schedule_source": "standalone|hems|none",
  "schedule_active": true,
  "next_period_start": "2025-12-04T22:00:00+01:00",
  "next_period_end": "2025-12-04T23:00:00+01:00",
  "current_power_kw": 0.0,
  "session_energy_kwh": 12.5,
  "ready_for_schedule": true,
  "last_hems_command_at": "2025-12-04T14:30:00+01:00"
}
```

## Risk Assessment

| Risk | Mitigation |
|------|------------|
| HEMS system offline | Expose `last_hems_command_at` sensor; optionally fall back to standalone after timeout (future enhancement) |
| Invalid HEMS schedule | Validate payload, reject malformed schedules, log errors, maintain last valid state |
| Mode switch while schedule active | Clear current schedule when switching modes, start fresh |
| Price threshold too restrictive | If no slots meet threshold, expose warning sensor; don't charge rather than exceed threshold |

## Success Criteria

- [ ] New `operation_mode` config option with `standalone` (default) and `hems` values
- [ ] New `price_threshold` config option (default 0.25 EUR/kWh, standalone mode only)
- [ ] Modified slot selection: top X unique price levels instead of top X slots
- [ ] HEMS mode subscribes to schedule topics and applies received schedules
- [ ] HEMS mode publishes status updates to status topic
- [ ] New sensors: `schedule_source`, `hems_connected`, `price_threshold_active`
- [ ] Mode switch clears current schedule and reinitializes
- [ ] Documentation updated with HEMS integration guide
- [ ] Unit tests for unique price selection and MQTT message handling
