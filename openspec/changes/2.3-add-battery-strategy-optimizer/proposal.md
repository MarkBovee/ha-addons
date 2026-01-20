# Battery Strategy Optimizer Add-on Proposal

**Version:** 2.3  
**Status:** 🟡 **IN PROGRESS - 82% COMPLETE**  
**Created:** 2026-01-20  
**Target Completion:** 2026-02-03  
**Completed Tasks:** 113 of 138  
**Last Updated:** 2026-01-20

---

## Executive Summary

This change introduces a new **battery-strategy** Home Assistant add-on that optimizes home battery charging and discharging based on dynamic electricity prices, weather conditions, solar production, grid import/export, and EV charger status. The add-on migrates core battery management logic from the existing NetDaemonApps C# implementation to a native Python add-on with a modular, maintainable architecture.

### Why This Change?

**Current State:**
- Battery optimization logic lives in NetDaemonApps (C# .NET 9.0) running as a separate service
- 1,438-line monolithic RangeBasedStrategy.cs class with complex interdependencies
- Requires .NET runtime and NetDaemon framework
- Difficult to test, debug, and maintain

**Desired State:**
- Standalone Python add-on following ha-addons architecture patterns
- 11 independent modules averaging <100 lines each with single responsibilities
- Pure functions for core calculations (testable without mocks)
- Native Home Assistant integration via MQTT Discovery
- Simple configuration via Home Assistant UI

**Key Benefits:**
- **Maintainability**: Small, focused modules vs. 1,438-line monolith
- **Testability**: Pure functions with no external dependencies for core logic
- **Integration**: Native HA entities via MQTT Discovery (proper unique_id support)
- **Simplicity**: Python-based, aligns with other add-ons (energy-prices, water-heater-scheduler)
- **Performance**: Removes .NET runtime dependency, runs on Alpine Linux base

---

## What's Changing

| Aspect | Before | After |
|--------|--------|-------|
| **Runtime** | .NET 9.0 + NetDaemon | Python 3.12+ native add-on |
| **Architecture** | 1,438-line RangeBasedStrategy class | 11 modular sub-routines (<100 lines each) |
| **Configuration** | JSON in NetDaemon appsettings | YAML in Home Assistant UI |
| **Entity Management** | NetDaemon REST API calls | MQTT Discovery (proper unique_id) |
| **Testing** | Complex mocking required | Pure functions testable in isolation |
| **Dependencies** | .NET runtime, NetDaemon framework | Python stdlib, requests, paho-mqtt |
| **Deployment** | Separate NetDaemon container | Standard HA add-on (via Supervisor) |

---

## Architecture Overview

### 11 Sub-Routine Modules

**Core Calculators (Pure Functions):**
1. **price_analyzer.py** - Sort price curve, find TopX cheapest/expensive periods
2. **temperature_advisor.py** - Map temperature to discharge hours (1-3 based on <0°C, <8°C, <16°C, <20°C, ≥20°C)
3. **power_calculator.py** - Rank-based power scaling (8000W rank 1 → 4000W minimum)
4. **soc_guardian.py** - Battery protection (5% minimum, 40% conservative, 20% end-of-day target)

**Monitoring Modules (Sensor Readers):**
5. **solar_monitor.py** - Detect excess solar production (>1000W surplus)
6. **grid_monitor.py** - Track grid import/export (prevent unwanted export)
7. **ev_charger_monitor.py** - Track EV charging, pause battery discharge when EV active (>500W)

**Integration Modules:**
8. **schedule_builder.py** - Combine price periods + temp hours + power levels into unified schedule
9. **schedule_publisher.py** - Convert to JSON format and publish to MQTT (battery_api/text/schedule/set)
10. **status_reporter.py** - Publish MQTT Discovery entities (status, reasoning, forecast, current_action)
11. **main.py** - Orchestrator with 2 functions: generate_schedule (hourly), monitor_active_period (1-min)

### Data Flow

```
energy-prices sensor (96-192 intervals)
    ↓
price_analyzer.py → TopX charge/discharge periods
    ↓
temperature_advisor.py → Effective discharge hours (1-3)
    ↓
schedule_builder.py → Combine periods + hours + SOC rules
    ↓
power_calculator.py → Apply rank-based scaling
    ↓
ev_charger_monitor.py → Pause discharge if EV charging
    ↓
schedule_publisher.py → MQTT battery_api/text/schedule/set
    ↓
Battery inverter executes schedule
    
(In parallel: monitor_active_period checks grid/solar/SOC every 1 min)
```

---

## Configuration Schema

```yaml
timing:
  update_interval: 3600  # Hourly schedule generation
  monitor_interval: 60   # Real-time monitoring (1 min)
  
power:
  max_charge_power: 8000     # Watts
  max_discharge_power: 8000  # Watts
  min_discharge_power: 4000  # Minimum to prevent wear
  
soc:
  min_soc: 5           # Hard minimum (%)
  conservative_soc: 40 # Conservative discharge threshold (%)
  target_eod_soc: 20   # End-of-day target (%)
  
heuristics:
  top_x_charge_hours: 3       # Number of cheapest periods
  top_x_discharge_hours: 2    # Number of most expensive periods
  excess_solar_threshold: 1000 # Watts surplus to trigger opportunistic charging
  
temperature_based_discharge:
  enabled: true
  thresholds:
    - temp_max: 0   # < 0°C
      discharge_hours: 1
    - temp_max: 8   # < 8°C
      discharge_hours: 1
    - temp_max: 16  # < 16°C
      discharge_hours: 2
    - temp_max: 20  # < 20°C
      discharge_hours: 2
    - temp_max: 999 # >= 20°C
      discharge_hours: 3
      
ev_charger:
  enabled: true
  charging_threshold: 500  # Watts (pause discharge if EV >500W)
  entity_id: "sensor.ev_charger_power"
```

---

## Smart Behaviors

### 1. EV Charger Awareness
**Scenario:** Expensive period + EV charging
- **Condition:** Price in top 3 expensive periods AND EV drawing >500W
- **Behavior:** Pause battery discharge (avoid round-trip losses)
- **Reasoning:** Battery → EV transfer loses ~20% efficiency vs. grid → EV direct

**Scenario:** Solar + EV charging
- **Condition:** Solar surplus >1000W AND EV charging
- **Behavior:** Allow solar export to EV, don't trigger battery charge
- **Reasoning:** Solar → EV direct is more efficient than Solar → Battery → EV

**Scenario:** Cheap period + EV not charging
- **Condition:** Price in bottom 3 periods AND EV idle
- **Behavior:** Battery charges at 8000W, EV can charge simultaneously
- **Reasoning:** Both battery and EV benefit from cheap grid power

### 2. Temperature-Based Discharge Duration
**Rationale:** Heating costs dominate in cold weather; discharge longer to offset heating load
- **<0°C:** 1 hour discharge (extreme cold, heating very expensive)
- **0-8°C:** 1 hour (moderate heating needs)
- **8-16°C:** 2 hours (lower heating, extend discharge)
- **16-20°C:** 2 hours (minimal heating)
- **≥20°C:** 3 hours (no heating, maximize discharge value)

### 3. Rank-Based Power Scaling
**Purpose:** Higher-ranked expensive periods get more aggressive discharge
- **Rank 1 (most expensive):** 8000W
- **Rank 2:** 6000W (75%)
- **Rank 3:** 4000W (50%)
- **Minimum:** 4000W (prevent battery wear from low-power cycling)

### 4. Excess Solar Opportunistic Charging
**Trigger:** Solar production - house load > 1000W
- **Action:** Enable battery charge to prevent grid export
- **Benefit:** Store surplus solar instead of exporting at low rates

### 5. Grid Export Prevention
**Trigger:** Grid power < -500W (exporting to grid)
- **Action:** Reduce battery discharge or pause
- **Benefit:** Avoid exporting battery power at unfavorable export prices

---

## Dependencies

### Data Sources (Home Assistant Entities)
- `sensor.energy_prices_electricity_import_price` - Price curve (96-192 intervals in attributes)
- `sensor.battery_api_state_of_charge` - Current SOC (%)
- `sensor.grid_power` - Import/export power (W, negative = export)
- `sensor.solar_power` - Solar production (W)
- `sensor.house_load_power` - House consumption (W)
- `sensor.weather_forecast_temperature` - Outdoor temperature (°C)
- `sensor.ev_charger_power` - EV charging power (W, 0 when idle)

### Integrations
- **energy-prices** add-on - Provides price data (already implemented)
- **battery-api** add-on - MQTT interface to SAJ inverter (already implemented)
- **MQTT broker** - Mosquitto add-on (required for MQTT Discovery)

### External APIs
- None (all data from Home Assistant entities)

---

## Breaking Changes

### Removed
- ❌ NetDaemon dependency (C# runtime no longer needed)
- ❌ REST API entity creation pattern (replaced by MQTT Discovery)

### Changed
- ⚠️ Configuration format: JSON → YAML
- ⚠️ Entity names: `battery.` prefix → `battery_strategy.` prefix
- ⚠️ Schedule format: Internal representation changes (MQTT JSON format unchanged)

### Migration Path
1. Keep NetDaemonApps battery app running during transition
2. Deploy battery-strategy add-on with `enabled: false` initially
3. Validate schedule output matches NetDaemon output for 24 hours
4. Switch `enabled: true` and stop NetDaemon battery app
5. Monitor for 1 week, rollback to NetDaemon if issues detected

---

## Risk Assessment

| Risk | Severity | Likelihood | Mitigation |
|------|----------|------------|------------|
| **Logic Errors** | High | Medium | Comprehensive unit tests for pure functions; integration tests with mock HA API |
| **Schedule Conflicts** | Medium | Low | Validate JSON format matches existing battery-api expectations |
| **MQTT Availability** | Medium | Low | Graceful degradation if MQTT unavailable; log warnings |
| **Price Data Missing** | Medium | Medium | Fallback to previous day's prices if energy-prices unavailable |
| **EV Integration Issues** | Low | Low | EV monitoring is optional (enabled: false disables feature) |
| **Battery Wear** | Medium | Low | SOC protection rules (5% min, 40% conservative threshold) |

**Testing Strategy:**
- ✅ Unit tests for all pure functions (price_analyzer, temperature_advisor, power_calculator, soc_guardian)
- ✅ Integration tests with mocked HA API
- ✅ Dry-run mode (log schedules without publishing to MQTT)
- ✅ Side-by-side comparison with NetDaemon output for 1 week

---

## Timeline

| Phase | Duration | Deliverable |
|-------|----------|-------------|
| **Phase 0: Setup** | 1 day | Branch created, OpenSpec structure validated |
| **Phase 1: Core Calculators** | 3 days | price_analyzer, temperature_advisor, power_calculator, soc_guardian + unit tests |
| **Phase 2: Monitoring** | 2 days | solar_monitor, grid_monitor, ev_charger_monitor + integration tests |
| **Phase 3: Integration** | 3 days | schedule_builder, schedule_publisher, status_reporter + MQTT Discovery |
| **Phase 4: Orchestrator** | 2 days | main.py with generate_schedule + monitor_active_period |
| **Phase 5: Configuration** | 1 day | config.yaml, Dockerfile, requirements.txt, README |
| **Phase 6: Testing** | 2 days | End-to-end tests, dry-run validation, side-by-side comparison |
| **Total** | **14 days** | Fully functional battery-strategy add-on |

**Target Completion:** 2026-02-03

---

## Success Criteria

✅ **Functional Requirements:**
- [ ] Generates charge/discharge schedules based on price curve TopX periods
- [ ] Adjusts discharge duration based on outdoor temperature (1-3 hours)
- [ ] Scales discharge power based on period rank (8000W → 4000W)
- [ ] Pauses battery discharge when EV charging detected (>500W)
- [ ] Opportunistic charging when excess solar >1000W
- [ ] Prevents grid export when grid power < -500W
- [ ] Publishes schedule to battery_api/text/schedule/set via MQTT
- [ ] Creates MQTT Discovery entities with unique_id

✅ **Quality Requirements:**
- [ ] All pure functions have unit tests (≥85% coverage)
- [ ] Integration tests for monitoring modules
- [ ] Dry-run mode validates logic without affecting battery
- [ ] Configuration schema validates on startup
- [ ] Graceful shutdown on SIGTERM/SIGINT

✅ **Operational Requirements:**
- [ ] README with setup instructions and troubleshooting
- [ ] Example configuration in README
- [ ] CHANGELOG with migration notes
- [ ] Side-by-side validation report comparing with NetDaemon output

---

## Version History

| Date | Version | Changes |
|------|---------|---------|
| 2026-01-20 | 2.3 | Initial proposal - migrate battery management from NetDaemonApps to Python add-on |

