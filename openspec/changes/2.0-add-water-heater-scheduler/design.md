# Design: Water Heater Scheduler Add-on

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

| Program | Condition | Target Temp |
|---------|-----------|-------------|
| Night | night_price < day_price | 56°C |
| Night | night_price >= day_price | 52°C |
| Day | price_level == None | 70°C |
| Day | price_level == Low/Medium/High | 58°C |
| Day | tomorrow_night < current AND price_level > Medium | idle (35°C) |
| Legionella | price_level == None | 70°C |
| Legionella | otherwise | 62°C |
| Away + Legionella | current_price < 0.2 | 66°C |
| Away + Legionella | current_price >= 0.2 | 60°C |
| Idle | always | 35°C |

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
