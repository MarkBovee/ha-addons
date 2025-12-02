# Design: Water Heater Scheduler Add-on

## User Settings (config.yaml)

### Entity Selection

| Key | Type | Default | Required | Description |
|-----|------|---------|----------|-------------|
| `water_heater_entity_id` | string | – | **Yes** | Target water_heater entity to control |
| `price_sensor_entity_id` | string | `sensor.ep_price_import` | No | Auto-detected if energy-prices add-on installed |
| `away_mode_entity_id` | string | – | No | Optional: away mode switch/input_boolean |
| `bath_mode_entity_id` | string | – | No | Optional: bath mode input_boolean |

**Smart Entity Detection:**
- Price sensor: Auto-detects `sensor.ep_price_import` if energy-prices add-on is present
- Water heater: Suggests entities matching `water_heater.*hot_water*` or `water_heater.*domestic*`
- If optional entities not configured, those features are simply disabled

### Schedule Settings

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `evaluation_interval_minutes` | integer | `5` | How often to re-evaluate (1-60) |
| `night_window_start` | string | `00:00` | Night program start time (HH:MM) |
| `night_window_end` | string | `06:00` | Night program end time (HH:MM) |
| `heating_duration_hours` | integer | `1` | Standard program duration (1-4) |
| `legionella_day` | select | `Saturday` | Day for weekly legionella cycle |
| `legionella_duration_hours` | integer | `3` | Legionella program duration (1-6) |
| `bath_auto_off_temp` | integer | `50` | Auto-disable bath mode above this °C |

### Temperature Presets

| Key | Type | Default | Options | Description |
|-----|------|---------|---------|-------------|
| `temperature_preset` | select | `comfort` | eco, comfort, performance, custom | Temperature profile |

**Preset Values:**

| Setting | Eco | Comfort (Legacy) | Performance |
|---------|-----|------------------|-------------|
| `night_preheat` | 52°C | 56°C | 60°C |
| `night_minimal` | 48°C | 52°C | 56°C |
| `day_preheat` | 55°C | 58°C | 60°C |
| `day_minimal` | 35°C | 35°C | 45°C |
| `legionella` | 60°C | 62°C | 66°C |

**Fixed Temperatures (all presets):**
| Condition | Temperature | Rationale |
|-----------|-------------|-----------|
| Negative/zero price | 70°C | Free energy - maximize heating |
| Bath mode active | 58°C | Comfortable bath temperature |
| Away mode | 35°C | Safe minimum while absent |
| Idle (between programs) | 35°C | Standby temperature |

### Custom Temperature Overrides

Only used when `temperature_preset: custom`:

| Key | Type | Default | Range | Description |
|-----|------|---------|-------|-------------|
| `night_preheat_temp` | integer | 56 | 45-65 | Night cheaper than day → heat more |
| `night_minimal_temp` | integer | 52 | 40-60 | Day cheaper → heat less at night |
| `day_preheat_temp` | integer | 58 | 50-70 | Today cheaper than tomorrow → heat more |
| `day_minimal_temp` | integer | 35 | 30-50 | Tomorrow cheaper → minimal heating |
| `legionella_temp` | integer | 62 | 60-70 | Weekly anti-bacterial target |

### Advanced Settings

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `min_cycle_gap_minutes` | integer | `50` | Minimum time between heating cycles (prevents rapid toggling) |
| `log_level` | select | `info` | Logging verbosity (debug/info/warning/error) |

**Cycle Gap Explained:**
The add-on tracks when the last heating cycle ended. A new program won't start until `min_cycle_gap_minutes` has passed. This prevents the heater from toggling on/off rapidly when prices fluctuate near thresholds.
- Default 50 minutes = ~10 evaluation cycles at 5-minute intervals (matches legacy `wait_cycles=10`)
- Set higher (90-120 min) for more stability, lower (30 min) for more responsiveness

### Configuration Validation

The add-on validates settings on startup and logs warnings:

| Check | Warning Message |
|-------|-----------------|
| `legionella_temp < 60` | "Legionella temp below 60°C may not be effective for sanitization" |
| `night_preheat < night_minimal` | "night_preheat should be higher than night_minimal" |
| `day_preheat < day_minimal` | "day_preheat should be higher than day_minimal" |
| Price sensor unavailable | "Price sensor not found - will retry each cycle" |
| Water heater unavailable | "Water heater entity not found - cannot start" |

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    water-heater-scheduler                    │
├─────────────────────────────────────────────────────────────┤
│  main.py (orchestration)                                    │
│    ├── Evaluation loop (configurable interval)              │
│    ├── Signal handlers (graceful shutdown)                  │
│    └── Sensor creation/updates                              │
├─────────────────────────────────────────────────────────────┤
│  scheduler.py (program selection)                           │
│    ├── Select program (Night/Day/Legionella/Bath/Away)      │
│    ├── Calculate target temperature from preset             │
│    ├── Apply cycle gap protection                           │
│    └── Track last cycle end time                            │
├─────────────────────────────────────────────────────────────┤
│  price_analyzer.py (price intelligence)                     │
│    ├── Parse price_curve from price sensor                  │
│    ├── Find lowest price in night/day windows               │
│    ├── Compare today vs tomorrow prices                     │
│    └── Detect negative/zero prices                          │
├─────────────────────────────────────────────────────────────┤
│  water_heater_controller.py (HA entity control)             │
│    ├── Set operation mode (Manual)                          │
│    ├── Set target temperature                               │
│    └── Read current temperature                             │
├─────────────────────────────────────────────────────────────┤
│  models.py (data structures)                                │
│    ├── ScheduleConfig (user settings + presets)             │
│    ├── ProgramType enum                                     │
│    ├── TemperaturePreset dataclass                          │
│    └── HeaterState (persistence)                            │
└─────────────────────────────────────────────────────────────┘
            │                           │
            ▼                           ▼
┌───────────────────────┐   ┌───────────────────────────────┐
│  energy-prices addon  │   │  Home Assistant Supervisor    │
│  sensor.ep_price_*    │   │  water_heater.*, switch.*     │
│  (auto-detected)      │   │  REST API /api/states/        │
└───────────────────────┘   └───────────────────────────────┘
```

## Programs

| Program | When Active | Purpose |
|---------|-------------|---------|
| **Night** | 00:00 - 06:00 (configurable) | Heat during off-peak hours |
| **Day** | 06:00 - 24:00 | Maintain comfort during daytime |
| **Legionella** | Weekly on configured day | Anti-bacterial high-temp cycle (60°C+) |
| **Bath** | When bath_mode entity is on | Boost to 58°C before bath (optional) |
| **Away** | When away_mode entity is on | Minimal 35°C while absent (optional) |
| **Idle** | Between programs | Maintain 35°C standby |

## Decision Logic

```
1. IF price ≤ 0 → 70°C (free energy - maximize!)
2. IF away_mode_entity is "on" → 35°C (Away)
3. IF bath_mode_entity is "on" AND current_temp < 58°C → 58°C (Bath)
   - Auto-disable bath_mode when temp reaches bath_auto_off_temp
4. IF legionella_day AND within program window → preset.legionella
5. IF night_window (00:00-06:00):
   - IF night_price < day_price → preset.night_preheat
   - ELSE → preset.night_minimal
6. IF day_window (06:00-24:00):
   - IF today_price < tomorrow_price → preset.day_preheat
   - ELSE → preset.day_minimal
7. ELSE → 35°C (Idle)

Cycle Gap Protection:
- Before starting any program, check if min_cycle_gap_minutes has passed
- If not, remain at current temperature until gap satisfied
```

## Price Data Contract

The add-on reads from `sensor.ep_price_import` (created by energy-prices add-on):

```json
{
  "state": "26.6307",
  "attributes": {
    "unit_of_measurement": "cents/kWh",
    "price_curve": {
      "2025-12-02T00:00:00+01:00": 22.5432,
      "2025-12-02T00:15:00+01:00": 21.8765,
      ...
    },
    "percentiles": {
      "p05": 18.2341,
      "p20": 21.5678,
      "p40": 24.8901,
      "p60": 28.1234,
      "p80": 32.4567,
      "p95": 38.7890
    },
    "price_level": "Medium"
  }
}
```

## State Persistence

Store in `/data/state.json` to survive container restarts:

```json
{
  "current_program": "Night",
  "target_temperature": 56,
  "last_cycle_end": "2025-12-02T03:30:00Z",
  "last_update": "2025-12-02T02:30:00Z"
}
```

## Output Sensors

The add-on creates these sensors (no external input helpers required):

| Entity ID | Type | Description |
|-----------|------|-------------|
| `sensor.wh_program` | sensor | Current program (Night/Day/Legionella/Bath/Away/Idle) |
| `sensor.wh_target_temp` | sensor | Current target temperature in °C |
| `sensor.wh_next_program` | sensor | Next scheduled program start time |
| `sensor.wh_status` | sensor | Human-readable status message |

## Error Handling Strategy

| Error | Response |
|-------|----------|
| Price sensor unavailable | Log warning, skip cycle, retry next interval |
| Price curve empty/missing | Use fallback: current hour pricing only |
| Water heater entity unavailable | Log error, skip cycle |
| HA API timeout | Retry once, then skip cycle |
| State file corrupt | Reset to defaults, log warning |
