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

### Decoded Register Mapping (from HAR Analysis)

The SAJ H2 inverter uses Modbus register addresses for battery schedule configuration. Through HAR file analysis, we've decoded the complete register mapping:

#### Register Structure

| Component | Register | Purpose |
|-----------|----------|----------|
| **Header** | `0x3647` | Enables time-of-use mode |
| **Charge Slot 1** | `0x3606`, `0x3607`, `0x3608` | First charge period |
| **Charge Slot 2** | `0x3609`, `0x360A`, `0x360B` | Second charge period |
| **Charge Slot 3** | `0x360C`, `0x360D`, `0x360E` | Third charge period |
| **Discharge Slot 1** | `0x361B`, `0x361C`, `0x361D` | First discharge period |
| **Discharge Slot 2** | `0x361E`, `0x361F`, `0x3620` | Second discharge period |
| **Discharge Slot 3** | `0x3621`, `0x3622`, `0x3623` | Third discharge period |
| **Discharge Slot 4** | `0x3624`, `0x3625`, `0x3626` | Fourth discharge period |
| **Discharge Slot 5** | `0x3627`, `0x3628`, `0x3629` | Fifth discharge period |
| **Discharge Slot 6** | `0x362A`, `0x362B`, `0x362C` | Sixth discharge period |

#### Pattern Format

Each slot uses 3 consecutive registers formatted as: `XXXX|YYYY|ZZZZ_ZZZZ`
- First register: Start time (encoded)
- Second register: End time (encoded)  
- Third register: Power setting (duplicated with underscore suffix)

**API Fields:**
- `commAddress`: Header + slot registers joined by `|`
- `componentId`: `|30|30|30_30` repeated per slot (4 values per register block)
- `transferId`: `|5|5|2_1` repeated per slot (data type markers)

### Supported Combinations

| Charges | Discharges | Use Case |
|---------|------------|----------|
| 0-3 | 0-6 | Any combination with at least 1 total period |

**Maximum:** 3 charge slots + 6 discharge slots

### Dynamic Address Generation (Python)

```python
# Register base addresses
HEADER_REGISTER = "3647"

CHARGE_SLOT_REGISTERS = [
    ["3606", "3607", "3608"],  # Slot 1
    ["3609", "360A", "360B"],  # Slot 2
    ["360C", "360D", "360E"],  # Slot 3
]

DISCHARGE_SLOT_REGISTERS = [
    ["361B", "361C", "361D"],  # Slot 1
    ["361E", "361F", "3620"],  # Slot 2
    ["3621", "3622", "3623"],  # Slot 3
    ["3624", "3625", "3626"],  # Slot 4
    ["3627", "3628", "3629"],  # Slot 5
    ["362A", "362B", "362C"],  # Slot 6
]

def generate_address_patterns(charge_count: int, discharge_count: int):
    """Generate SAJ API address patterns dynamically."""
    if not is_supported_pattern(charge_count, discharge_count):
        raise ValueError(f"Unsupported: {charge_count} charges + {discharge_count} discharges")
    
    comm_parts = [HEADER_REGISTER]
    component_parts = []
    transfer_parts = []
    
    # Add charge slots
    for i in range(charge_count):
        regs = CHARGE_SLOT_REGISTERS[i]
        comm_parts.append(f"{regs[0]}|{regs[1]}|{regs[2]}_{regs[2]}")
        component_parts.append("|30|30|30_30")
        transfer_parts.append("|5|5|2_1")
    
    # Add discharge slots
    for i in range(discharge_count):
        regs = DISCHARGE_SLOT_REGISTERS[i]
        comm_parts.append(f"{regs[0]}|{regs[1]}|{regs[2]}_{regs[2]}")
        component_parts.append("|30|30|30_30")
        transfer_parts.append("|5|5|2_1")
    
    return {
        "comm_address": "|".join(comm_parts),
        "component_id": "".join(component_parts),
        "transfer_id": "".join(transfer_parts)
    }

def is_supported_pattern(charges: int, discharges: int) -> bool:
    """Check if charge/discharge combination is supported."""
    return (0 <= charges <= 3 and 
            0 <= discharges <= 6 and 
            charges + discharges > 0)
```

### Example Patterns

**1 Charge + 1 Discharge (1+1):**
```
comm_address: 3647|3606|3607|3608_3608|361B|361C|361D_361D
component_id: |30|30|30_30|30|30|30_30
transfer_id:  |5|5|2_1|5|5|2_1
```

**2 Charges + 3 Discharges (2+3):**
```
comm_address: 3647|3606|3607|3608_3608|3609|360A|360B_360B|361B|361C|361D_361D|361E|361F|3620_3620|3621|3622|3623_3623
component_id: |30|30|30_30|30|30|30_30|30|30|30_30|30|30|30_30|30|30|30_30
transfer_id:  |5|5|2_1|5|5|2_1|5|5|2_1|5|5|2_1|5|5|2_1
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
