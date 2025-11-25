# Design: Battery API Add-on

## Overview

This document captures the technical architecture and design decisions for the Battery API add-on.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         Home Assistant                               │
│  ┌───────────────┐  ┌───────────────┐  ┌───────────────────────────┐│
│  │ Control       │  │ Status        │  │ Existing Entities         ││
│  │ Entities      │  │ Entities      │  │ (read-only)               ││
│  │               │  │               │  │                           ││
│  │ number.ba_*   │  │ sensor.ba_*   │  │ sensor.epex (prices)      ││
│  │ select.ba_*   │  │               │  │ sensor.inverter_* (SAJ)   ││
│  │ button.ba_*   │  │               │  │ sun.sun                   ││
│  └───────┬───────┘  └───────▲───────┘  └───────────▲───────────────┘│
│          │                  │                      │                 │
│          │ MQTT subscribe   │ MQTT publish         │ REST API read   │
│          ▼                  │                      │                 │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │                    Battery API Add-on                          │  │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐ │  │
│  │  │ MQTT        │  │ SAJ API     │  │ HA REST Client          │ │  │
│  │  │ Discovery   │  │ Client      │  │ (read existing entities)│ │  │
│  │  │ Publisher   │  │             │  │                         │ │  │
│  │  └──────┬──────┘  └──────┬──────┘  └───────────┬─────────────┘ │  │
│  │         │                │                     │               │  │
│  │         ▼                ▼                     ▼               │  │
│  │  ┌─────────────────────────────────────────────────────────┐   │  │
│  │  │                    Main Loop                             │   │  │
│  │  │  - Poll SAJ API every 60s for status                    │   │  │
│  │  │  - Watch MQTT for control entity changes                │   │  │
│  │  │  - Apply schedule when button pressed or inputs change  │   │  │
│  │  └─────────────────────────────────────────────────────────┘   │  │
│  └───────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
                                    │
                                    │ HTTPS
                                    ▼
                    ┌───────────────────────────────┐
                    │   SAJ Electric Cloud API      │
                    │   https://eop.saj-electric.com│
                    │                               │
                    │   - Authentication (OAuth)    │
                    │   - Get device status         │
                    │   - Get/Set schedule          │
                    │   - Get user mode             │
                    └───────────────────────────────┘
```

---

## Design Decisions

### 1. Entity-Based Control (No REST API)

**Decision:** Use Home Assistant entities for control instead of exposing a REST API.

**Rationale:**
- Simpler architecture (no HTTP server in add-on)
- Native HA automations can interact with entities directly
- Consistent with energy-prices add-on pattern
- MQTT Discovery provides `unique_id` support for UI management

**Alternatives Considered:**
- REST API: More flexible but requires HTTP server, authentication, adds complexity
- WebSocket: Real-time but overkill for battery control

### 2. MQTT Number/Select/Button Entities for Control

**Decision:** Use MQTT `number`, `select`, and `button` components instead of `input_*` helpers.

**Rationale:**
- MQTT Discovery natively supports these entity types with command topics
- `input_*` helpers require REST API calls to create and don't integrate with MQTT
- MQTT entities have proper `unique_id` for HA UI management
- User doesn't need to pre-create helpers in configuration.yaml

**Entity Types:**
| HA Entity Type | MQTT Component | Purpose |
|----------------|----------------|---------|
| `number` | `number` | Power (W), Duration (min) |
| `select` | `select` | Charge type (Charge/Discharge) |
| `button` | `button` | Apply schedule trigger |
| `sensor` | `sensor` | SOC, mode, direction (read-only) |

### 3. Simple Schedule Model (v1)

**Decision:** Support only single charge + single discharge periods in v1.

**Rationale:**
- SAJ API has complex pattern requirements (1+1, 1+2, 2+1, etc.)
- Simple model covers 80% of use cases
- Complex multi-period scheduling stays in NetDaemon
- Reduces implementation complexity significantly

**v1 Limitations:**
- Maximum 1 charge period + 1 discharge period per schedule
- Day-specific scheduling not supported (all days enabled)
- No adaptive power adjustments

**Future Extensions (v2+):**
- Multiple periods via JSON input entity
- Day-specific scheduling
- Integration with NetDaemon for advanced strategies

### 4. SAJ API Client Porting Strategy

**Decision:** Port the C# `BatteryApi.cs` implementation to Python closely.

**Key Components to Port:**
1. **Authentication** (`Authenticate()`)
   - AES password encryption with fixed key
   - Signature calculation (MD5 + SHA1)
   - Token storage in file with expiry
   
2. **API Calls**
   - `GetUserModeAsync()` → `get_user_mode()`
   - `SaveBatteryScheduleAsync()` → `save_schedule()`
   - `GetCurrentScheduleAsync()` → `get_current_schedule()`

3. **Schedule Building** (`BuildBatteryScheduleParameters()`)
   - Period ordering (charges first, then discharges)
   - Address pattern generation based on charge/discharge counts
   - Value string formatting

**Python Libraries:**
- `pycryptodome` for AES encryption (replaces .NET Aes)
- `requests` for HTTP (existing pattern)
- `hashlib` for MD5/SHA1 (stdlib)

### 5. Token Storage

**Decision:** Store SAJ token in file (`/data/saj-token.json`) with expiry tracking.

**Format:**
```json
{
  "token": "eyJhbGciOiJIUzI1...",
  "expires_in": 86400,
  "expires_at_utc": "2025-11-26T20:00:00Z"
}
```

**Rationale:**
- Survives add-on restarts
- Matches NetDaemon pattern
- Proactive refresh before expiry (24h buffer)

---

## Entity Design

### Control Entities (User Input)

| Entity ID | Type | Range/Options | Default | Description |
|-----------|------|---------------|---------|-------------|
| `number.ba_charge_power_w` | number | 0–8000 | 6000 | Charge power in watts |
| `number.ba_charge_duration_min` | number | 0–360 | 60 | Charge duration in minutes |
| `text.ba_charge_start_time` | text | HH:MM | "00:00" | Charge start time |
| `number.ba_discharge_power_w` | number | 0–8000 | 6000 | Discharge power in watts |
| `number.ba_discharge_duration_min` | number | 0–360 | 60 | Discharge duration in minutes |
| `text.ba_discharge_start_time` | text | HH:MM | "00:00" | Discharge start time |
| `select.ba_schedule_type` | select | Charge Only / Discharge Only / Both / Clear | Both | What to include in schedule |
| `button.ba_apply_schedule` | button | — | — | Apply the configured schedule |

### Status Entities (Read-Only)

| Entity ID | Type | Unit | Description |
|-----------|------|------|-------------|
| `sensor.ba_battery_soc` | sensor | % | Current state of charge |
| `sensor.ba_battery_mode` | sensor | — | Current user mode (EMS, TimeOfUse, etc.) |
| `sensor.ba_charge_direction` | sensor | — | Current direction (charging/discharging/idle) |
| `sensor.ba_current_schedule` | sensor | — | Human-readable current schedule |
| `sensor.ba_last_applied` | sensor | — | Timestamp of last successful apply |
| `sensor.ba_api_status` | sensor | — | API connection status |

### Entity Attributes

**`sensor.ba_battery_soc` attributes:**
```json
{
  "battery_power_w": 2500,
  "grid_power_w": -1500,
  "last_updated": "2025-11-25T20:15:00Z"
}
```

**`sensor.ba_current_schedule` attributes:**
```json
{
  "periods": [
    {"type": "charge", "start": "02:00", "end": "04:00", "power_w": 6000},
    {"type": "discharge", "start": "17:00", "end": "21:00", "power_w": 8000}
  ],
  "source": "battery-api-addon",
  "applied_at": "2025-11-25T01:30:00Z"
}
```

---

## SAJ API Patterns

### Supported Schedule Patterns

The SAJ API requires specific combinations of charge and discharge periods:

| Pattern | Charges | Discharges | Use Case |
|---------|---------|------------|----------|
| 1+1 | 1 | 1 | Standard day (charge overnight, discharge peak) |
| 1+2 | 1 | 2 | Split discharge (morning + evening peaks) |
| 2+1 | 2 | 1 | Dual rate charging (night + solar top-up) |
| 1+0 | 1 | 0 | Charge only (no discharge periods) |
| 0+1 | 0 | 1 | Discharge only (no charge periods) |

**v1 Implementation:** Support 1+1, 1+0, 0+1 patterns only.

### Address Mapping

Each pattern requires specific register addresses for the SAJ API:

```python
ADDRESS_PATTERNS = {
    (1, 1): {
        "comm_address": "3647|3606|3607|3608_3608|361B|361C|361D_361D",
        "component_id": "|30|30|30_30|30|30|30_30",
        "transfer_id": "|5|5|2_1|5|5|2_1"
    },
    (1, 0): {
        "comm_address": "3647|3606|3607|3608_3608",
        "component_id": "|30|30|30_30",
        "transfer_id": "|5|5|2_1"
    },
    (0, 1): {
        "comm_address": "3647|361B|361C|361D_361D",
        "component_id": "|30|30|30_30",
        "transfer_id": "|5|5|2_1"
    }
}
```

---

## Configuration Schema

```yaml
# config.yaml options schema
options:
  saj_username: ""
  saj_password: ""
  device_serial_number: ""
  plant_uid: ""
  poll_interval_seconds: 60
  log_level: "info"
  simulation_mode: false

schema:
  saj_username: str
  saj_password: password
  device_serial_number: str
  plant_uid: str
  poll_interval_seconds: int(30,300)?
  log_level: list(debug|info|warning|error)?
  simulation_mode: bool?
```

---

## Error Handling

### API Errors

| Error Type | Detection | Response |
|------------|-----------|----------|
| Network timeout | `requests.Timeout` | Retry with backoff, update `sensor.ba_api_status` |
| Auth failure | HTTP 401, token expired | Re-authenticate, retry once |
| Invalid schedule | API returns error | Log error, update status entity, don't retry |
| Rate limiting | HTTP 429 | Exponential backoff |

### Entity State on Error

When API is unavailable:
- Status sensors: Keep last known value, add `unavailable_since` attribute
- Control entities: Remain functional (queued for next successful connection)
- `sensor.ba_api_status`: Set to "Disconnected" with error details

---

## Future Considerations

### v2 Features (Not in Scope)
- Multi-period scheduling via JSON input
- Day-specific scheduling
- Adaptive power based on consumption
- Integration with energy-prices add-on for automatic optimization
- EMS mode toggle control

### Integration Points
- **energy-prices add-on:** Could read price data for smart scheduling
- **NetDaemon:** Can delegate complex strategies, use add-on for execution
- **HA Automations:** Native entity-based control enables rich automation
