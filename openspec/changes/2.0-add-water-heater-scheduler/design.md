# Design: Water Heater Scheduler Add-on

## User Settings (config.yaml)

### Entity Selection
| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `price_sensor_entity_id` | select | `sensor.ep_price_import` | Energy price sensor with price_curve attribute |
| `water_heater_entity_id` | select | – (required) | Target water_heater entity to control |
| `away_mode_entity_id` | select | `switch.our_home_away_mode` | Away mode source switch/input_boolean |
| `bath_mode_entity_id` | select | `input_boolean.bath` | Bath override toggle |
| `status_text_entity_id` | string | `input_text.heating_schedule_status` | Status output text entity |

### Schedule Settings
| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `schedule_interval_minutes` | integer | `5` | Frequency of re-evaluation (1-60) |
| `night_window_start` | string | `00:00` | Night window start time (HH:MM) |
| `night_window_end` | string | `06:00` | Night window end time (HH:MM) |
| `legionella_day_of_week` | select | `Saturday` | Day to run legionella protection |
| `legionella_duration_hours` | integer | `3` | Length of legionella boost (1-6) |
| `heating_duration_hours` | integer | `1` | Standard program duration (1-4) |
| `next_day_price_check` | boolean | `true` | Compare tomorrow's price before day program |

### Temperature Settings
| Key | Type | Default | Range | Description |
|-----|------|---------|-------|-------------|
| `temp_idle` | integer | `35` | 30-45 | Idle/standby temperature |
| `temp_night_program` | integer | `56` | 45-65 | Target for night charge |
| `temp_night_program_low` | integer | `52` | 45-60 | Night target when night > day price |
| `temp_day_program` | integer | `58` | 50-70 | Target for daytime heating |
| `temp_day_program_max` | integer | `70` | 60-75 | Max temp for very low prices |
| `temp_legionella` | integer | `62` | 60-70 | Legionella cycle target |
| `temp_legionella_max` | integer | `70` | 65-75 | Legionella at very low prices |
| `temp_away_legionella` | integer | `60` | 55-66 | Away-mode legionella (expensive) |
| `temp_away_legionella_cheap` | integer | `66` | 60-70 | Away-mode legionella (cheap price) |
| `temp_bath_threshold` | integer | `50` | 45-60 | Auto-disable bath above this temp |

### Advanced Settings
| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `wait_cycles_limit` | integer | `10` | Cycles before forcing idle (5-20) |
| `cheap_price_threshold` | float | `0.20` | EUR/kWh threshold for "cheap" classification |
| `log_level` | select | `info` | Logging verbosity (debug/info/warning/error) |

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    water-heater-scheduler                    │
├─────────────────────────────────────────────────────────────┤
│  main.py (orchestration)                                    │
│    ├── 5-minute evaluation loop                             │
│    ├── Signal handlers (graceful shutdown)                  │
│    └── Entity creation/updates                              │
├─────────────────────────────────────────────────────────────┤
│  scheduler.py (program selection)                           │
│    ├── Determine program type (Night/Day/Legionella/Away)   │
│    ├── Calculate start/end times                            │
│    └── Apply temperature rules                              │
├─────────────────────────────────────────────────────────────┤
│  price_analyzer.py (price window detection)                 │
│    ├── Parse price_curve from energy-prices sensor          │
│    ├── Find lowest night price (00:00-06:00)                │
│    ├── Find lowest day price (06:00-24:00)                  │
│    └── Compare tomorrow vs today prices                     │
├─────────────────────────────────────────────────────────────┤
│  water_heater_controller.py (HA entity control)             │
│    ├── Set operation mode (Manual)                          │
│    ├── Set target temperature                               │
│    └── Read current temperature                             │
├─────────────────────────────────────────────────────────────┤
│  models.py (data structures)                                │
│    ├── ScheduleConfig (user settings)                       │
│    ├── ProgramType enum                                     │
│    ├── HeaterState (persistence)                            │
│    └── PriceWindow (start, end, price)                      │
└─────────────────────────────────────────────────────────────┘
            │                           │
            ▼                           ▼
┌───────────────────────┐   ┌───────────────────────────────┐
│  energy-prices addon  │   │  Home Assistant Supervisor    │
│  sensor.ep_price_*    │   │  water_heater.*, input_*.*   │
│  (price_curve attr)   │   │  REST API /api/states/       │
└───────────────────────┘   └───────────────────────────────┘
```

## Program Selection Logic

Ported from `WaterHeater.cs`, the scheduling follows this decision tree:

```
1. Check time of day
   ├── Hour < 6 → Night Program
   └── Hour >= 6
       ├── Saturday (configurable) → Legionella Program
       └── Otherwise → Day Program

2. Apply away mode override
   └── If switch.our_home_away_mode == "on" → Away temperatures

3. Apply bath mode check
   └── If input_boolean.bath == "on" AND current_temp > 50°C
       → Turn off bath mode automatically
```

## Temperature Decision Matrix

All temperatures are configurable via settings. Defaults shown:

| Program | Condition | Config Key | Default |
|---------|-----------|------------|---------|
| Night | night_price < day_price | `temp_night_program` | 56°C |
| Night | night_price >= day_price | `temp_night_program_low` | 52°C |
| Day | price_level == None | `temp_day_program_max` | 70°C |
| Day | price_level == Low/Medium/High | `temp_day_program` | 58°C |
| Day | tomorrow cheaper & price > Medium | `temp_idle` | 35°C |
| Legionella | price_level == None | `temp_legionella_max` | 70°C |
| Legionella | otherwise | `temp_legionella` | 62°C |
| Away + Legionella | price < `cheap_price_threshold` | `temp_away_legionella_cheap` | 66°C |
| Away + Legionella | price >= `cheap_price_threshold` | `temp_away_legionella` | 60°C |
| Idle | always | `temp_idle` | 35°C |
| Bath auto-off | current_temp > threshold | `temp_bath_threshold` | 50°C |

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
  "heater_on": true,
  "target_temperature": 56,
  "wait_cycles": 7,
  "last_program": "Night",
  "last_update": "2025-12-02T02:30:00Z"
}
```

## Wait Cycle Mechanism

To prevent rapid toggling between heating and idle:

1. When program ends, set `wait_cycles = 10` (configurable)
2. Each 5-minute cycle decrements `wait_cycles`
3. Only transition to idle when `wait_cycles == 0`
4. If new program starts, reset `wait_cycles`

## Entity Naming Convention

All entities use `wh_` prefix for water-heater-scheduler:

| Entity ID | Type | Description |
|-----------|------|-------------|
| `sensor.wh_program_type` | sensor | Current program (Night/Day/Legionella/Away/Idle) |
| `sensor.wh_target_temp` | sensor | Current target temperature in °C |
| `sensor.wh_next_start` | sensor | Next program start time (ISO timestamp) |
| `sensor.wh_next_end` | sensor | Next program end time (ISO timestamp) |
| `input_text.heating_schedule_status` | input_text | Human-readable status (legacy compatible) |

## Error Handling Strategy

| Error | Response |
|-------|----------|
| Price sensor unavailable | Log warning, skip cycle, retry next interval |
| Price curve empty/missing | Use fallback: current hour pricing only |
| Water heater entity unavailable | Log error, skip cycle |
| HA API timeout | Retry once, then skip cycle |
| State file corrupt | Reset to defaults, log warning |
