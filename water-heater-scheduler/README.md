# Water Heater Scheduler

Schedule domestic hot water heating based on electricity prices. This add-on optimizes heating costs while maintaining comfort and safety (legionella protection).

## Features

- **Price-based scheduling**: Heat water during cheapest electricity periods
- **Temperature presets**: Choose from eco, comfort, performance, or custom profiles
- **Night/Day programs**: Automatically selects optimal heating times
- **Dynamic window mode**: Optional automatic selection of day vs night based on prices
- **Legionella protection**: Weekly high-temperature sanitization cycle
- **Away mode**: Minimal heating while you're away
- **Bath mode**: Boost heating before baths with auto-disable
- **Cycle gap protection**: Prevents rapid on/off toggling

## Requirements

- **Energy Prices add-on**: Must be installed and running to provide price data via `sensor.ep_price_import`
- **Water heater entity**: A Home Assistant `water_heater.*` entity that supports `set_temperature` service

## Installation

1. Add this repository to Home Assistant Add-on Store
2. Install "Water Heater Scheduler"
3. Configure your water heater entity (see Configuration below)
4. Start the add-on

## Configuration

### Configuration UI at a Glance

The add-on now uses Home Assistant's selector-based form so the most important fields stay at the top and everything else is tucked under the **Advanced** toggle. Highlights:

- **Entity pickers** for the water heater and price sensor prevent typos and let you pick the right sensor (choose the Energy Prices import sensor if yours differs from the default `sensor.ep_price_import`).
- **Helper entity selectors** (Away/Bath switches) accept either `switch` or `input_boolean` entities and live under the Advanced section.
- **Schedule tuning & custom temperatures** sit in Advanced, so the default view only shows the essentials: heater entity, price sensor, preset, and Dynamic Window Mode toggle.

Switch the form to Advanced if you need to change timing windows, legionella settings, MQTT credentials, or provide custom temperatures.

### Basic Setup

```yaml
water_heater_entity_id: "water_heater.your_heat_pump"
price_sensor_entity_id: "sensor.ep_price_import"  # Auto-detected if energy-prices installed
temperature_preset: "comfort"
```

### Temperature Presets

| Setting | Eco | Comfort | Performance |
|---------|-----|---------|-------------|
| Night preheat | 52°C | 56°C | 60°C |
| Night minimal | 48°C | 52°C | 56°C |
| Day preheat | 55°C | 58°C | 60°C |
| Day minimal | 35°C | 35°C | 45°C |
| Legionella | 60°C | 62°C | 66°C |

**Fixed temperatures (all presets):**
- Negative/zero price: 70°C (free energy - maximize!)
- Bath mode: 58°C
- Away mode: 35°C
- Idle: 35°C

### Optional Mode Entities

```yaml
# Away mode - switch to minimal heating
away_mode_entity_id: "switch.our_home_away_mode"

# Bath mode - boost to 58°C before baths
bath_mode_entity_id: "input_boolean.bath"
```

### Schedule Settings

```yaml
evaluation_interval_minutes: 5     # How often to check (1-60)
night_window_start: "00:00"        # Night program window
night_window_end: "06:00"
heating_duration_hours: 1          # Standard program duration (1-4)
legionella_day: "Saturday"         # Weekly sanitization day
legionella_duration_hours: 3       # Legionella cycle duration (1-6)
bath_auto_off_temp: 50             # Auto-disable bath mode above this temp
```

### Custom Temperatures

When `temperature_preset: custom`, you can specify individual temperatures:

```yaml
temperature_preset: "custom"
night_preheat_temp: 58
night_minimal_temp: 54
day_preheat_temp: 60
day_minimal_temp: 38
legionella_temp: 65
```

### Advanced Settings

```yaml
min_cycle_gap_minutes: 50  # Minimum time between heating cycles (10-180)
log_level: "info"          # debug/info/warning/error
dynamic_window_mode: false # When true, pick the cheapest day or night window automatically
```

### Dynamic Window Mode

When `dynamic_window_mode: true`, the scheduler no longer relies on the current time of day to decide between the night or day program. Instead, it compares the full price curve every cycle and:

1. Picks the cheaper window (night or day) for the next heating run
2. Plans the run for the cheapest slot inside that window
3. Updates `sensor.wh_status` with the selected window and lowest price

This keeps the add-on independent from the Price Helper while still adjusting automatically between “winter nights” and “summer days.” The option defaults to `false` to preserve legacy behavior.

## How It Works

### Decision Tree

The add-on evaluates conditions in this order:

1. **Negative/zero price** → Heat to 70°C (free energy!)
2. **Away mode active** → 35°C (+ legionella on scheduled day)
3. **Bath mode active** → 58°C (auto-disables when target reached)
4. **Legionella day** → Weekly high-temp cycle (configurable day)
5. **Night window** → Compare night vs day prices for preheat decision
6. **Day window** → Compare today vs tomorrow prices
7. **Otherwise** → Idle at 35°C

### Night Program Logic

During the night window (default 00:00-06:00):
- If **night prices < day prices**: Preheat to higher temp (save money tomorrow)
- If **day prices < night prices**: Minimal heating (cheaper to heat during day)

### Day Program Logic

During the day window (06:00-24:00):
- If **today's prices < tomorrow's**: Preheat more (heating cheaper today)
- If **tomorrow's prices < today's**: Minimal heating (wait for tomorrow)

### Cycle Gap Protection

To prevent the water heater from toggling rapidly:
- After a heating cycle ends, a new one won't start for `min_cycle_gap_minutes`
- Default: 50 minutes (matches legacy 10 wait cycles at 5-minute intervals)
- Increase to 90-120 minutes for more stability

## Sensors Created

| Entity | Description |
|--------|-------------|
| `sensor.wh_program` | Current program (Night/Day/Legionella/Bath/Away/Idle) |
| `sensor.wh_target_temp` | Current target temperature in °C |
| `sensor.wh_status` | Human-readable status message (planned window, target, reason) |

## Local Testing

```bash
# From repository root
python run_addon.py --addon water-heater-scheduler --once

# Or run continuously
python run_addon.py --addon water-heater-scheduler
```

Required environment variables in `.env`:
```
HA_API_URL=http://your-ha-instance:8123/api
HA_API_TOKEN=your-long-lived-token
```

## Migrating from NetDaemon WaterHeater

This add-on replaces the NetDaemon `WaterHeater.cs` app. Key differences:

| Aspect | NetDaemon | This Add-on |
|--------|-----------|-------------|
| Runtime | C# / NetDaemon | Python / Home Assistant |
| Price data | `IPriceHelper` | `sensor.ep_price_import` |
| Configuration | C# code | YAML UI |
| Status | `input_text.heating_schedule_status` | `sensor.wh_status` |

To migrate:
1. Install and configure this add-on
2. Verify it's working correctly
3. Disable the NetDaemon WaterHeater app

## Troubleshooting

### Price sensor unavailable
- Ensure Energy Prices add-on is running
- Check `sensor.ep_price_import` has `price_curve` attribute

### Water heater not responding
- Verify entity ID is correct
- Check water heater supports `set_temperature` service
- Test manually in Developer Tools > Services

### Bath mode not turning off
- Check `bath_auto_off_temp` setting
- Verify water heater reports `current_temperature` attribute

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for version history.
