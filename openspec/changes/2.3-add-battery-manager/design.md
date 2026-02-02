# Battery Strategy Optimizer - Design Document

**Version:** 2.3  
**Last Updated:** 2026-01-20

---

## Architectural Overview

This document captures the key technical decisions and design patterns for the battery-strategy add-on. The design prioritizes **simplicity, testability, and maintainability** over feature completeness.

---

## Design Principles

### 1. Modular Architecture
**Decision:** Break 1,438-line monolithic C# class into 11 independent Python modules (<100 lines each)

**Rationale:**
- **Maintainability:** Small modules easier to understand and modify
- **Testability:** Pure functions testable without mocks or external dependencies
- **Debugging:** Isolate issues to specific modules
- **Reusability:** Modules can be used independently or combined

**Trade-offs:**
- ✅ **Pro:** Simpler mental model, easier onboarding for new developers
- ✅ **Pro:** Unit tests run faster (no setup/teardown overhead)
- ⚠️ **Con:** More files to manage (11 modules vs. 1 class)
- ⚠️ **Con:** Slightly more overhead passing data between functions

**Implementation:**
- Pure functions in `price_analyzer.py`, `temperature_advisor.py`, `power_calculator.py`, `soc_guardian.py`
- Sensor readers in `solar_monitor.py`, `grid_monitor.py`, `ev_charger_monitor.py`
- Integration in `schedule_builder.py`, `schedule_publisher.py`, `status_reporter.py`
- Orchestrator in `main.py`

---

### 2. Pure Functions for Core Logic
**Decision:** Core calculations (price analysis, power scaling, SOC protection) are pure functions with no side effects

**Rationale:**
- **Testability:** No mocks needed for unit tests
- **Predictability:** Same inputs → same outputs (no hidden state)
- **Parallelization:** Pure functions safe for concurrent execution
- **Reasoning:** Easier to understand function behavior

**Example:**
```python
# Pure function - no external dependencies
def calculate_scaled_power(rank: int, max_power: int, min_power: int) -> int:
    """Calculate discharge power based on period rank.
    
    Args:
        rank: Period rank (1 = most expensive, 2 = second, etc.)
        max_power: Maximum discharge power (e.g., 8000W)
        min_power: Minimum discharge power (e.g., 4000W)
        
    Returns:
        Scaled power in watts (max_power / rank, minimum min_power)
    """
    return max(max_power // rank, min_power)
```

**Trade-offs:**
- ✅ **Pro:** Instant feedback in tests (no setup/teardown)
- ✅ **Pro:** Confident refactoring (break tests = visible breakage)
- ⚠️ **Con:** Data must be explicitly passed (no global state)

---

### 3. Separation of Concerns
**Decision:** Clear boundaries between data retrieval, calculation, and integration

**Layers:**
1. **Data Readers** (sensors) - `solar_monitor.py`, `grid_monitor.py`, `ev_charger_monitor.py`
2. **Calculators** (pure functions) - `price_analyzer.py`, `temperature_advisor.py`, `power_calculator.py`, `soc_guardian.py`
3. **Builders** (assembly) - `schedule_builder.py`
4. **Publishers** (output) - `schedule_publisher.py`, `status_reporter.py`
5. **Orchestrator** (coordination) - `main.py`

**Rationale:**
- **Testing:** Mock only at layer boundaries (HA API, MQTT client)
- **Flexibility:** Swap implementations without affecting other layers
- **Clarity:** Function purpose obvious from module name

**Data Flow:**
```
Sensors → Calculators → Builders → Publishers → Battery/HA
  ↓          ↓            ↓           ↓
(HA API)  (Pure)      (Combine)   (MQTT)
```

---

### 4. Configuration-Driven Behavior
**Decision:** All tuning parameters externalized to `config.yaml` with schema validation

**Rationale:**
- **Flexibility:** Users can adjust without code changes
- **Safety:** Schema validation prevents invalid configurations
- **Documentation:** Config options self-document the system

**Configuration Sections:**
```yaml
timing:
  update_interval: 3600  # Hourly schedule generation
  monitor_interval: 60   # Real-time monitoring
  
power:
  max_charge_power: 8000
  max_discharge_power: 8000
  min_discharge_power: 4000
  
soc:
  min_soc: 5
  conservative_soc: 40
  target_eod_soc: 20
  
heuristics:
  top_x_charge_hours: 3
  top_x_discharge_hours: 2
  excess_solar_threshold: 1000
  
temperature_based_discharge:
  enabled: true
  thresholds:
    - {temp_max: 0, discharge_hours: 1}
    - {temp_max: 8, discharge_hours: 1}
    - {temp_max: 16, discharge_hours: 2}
    - {temp_max: 20, discharge_hours: 2}
    - {temp_max: 999, discharge_hours: 3}
    
ev_charger:
  enabled: true
  charging_threshold: 500
  entity_id: "sensor.ev_charger_power"
```

**Trade-offs:**
- ✅ **Pro:** Non-technical users can tune behavior
- ✅ **Pro:** A/B testing different strategies (change config, compare results)
- ⚠️ **Con:** More validation logic needed
- ⚠️ **Con:** Users could configure invalid states (mitigated by schema validation)

---

### 5. MQTT Discovery for Entity Management
**Decision:** Use MQTT Discovery instead of REST API for creating Home Assistant entities

**Rationale:**
- **unique_id Support:** MQTT Discovery entities have proper unique_id (REST API does not)
- **Persistence:** Users can rename, hide, or customize entities in HA UI
- **Standards:** MQTT Discovery is the recommended HA integration pattern
- **Device Grouping:** All entities grouped under one device in HA UI

**Discovery Payload Example:**
```json
{
  "name": "Battery Strategy Status",
  "unique_id": "battery_strategy_status",
  "state_topic": "battery-strategy/sensor/status/state",
  "device_class": "enum",
  "device": {
    "identifiers": ["battery_strategy_addon"],
    "name": "Battery Strategy Optimizer",
    "manufacturer": "HA Addons",
    "model": "SAJ Battery Optimizer"
  }
}
```

**Trade-offs:**
- ✅ **Pro:** Proper unique_id enables UI management
- ✅ **Pro:** Entities persist across restarts
- ✅ **Pro:** Device grouping in HA UI
- ⚠️ **Con:** Requires MQTT broker (Mosquitto add-on)
- ⚠️ **Con:** Slightly more complex setup vs. REST API

---

### 6. EV Charger Integration
**Decision:** Monitor EV charger sensor and pause battery discharge when EV charging >500W

**Rationale:**
- **Efficiency:** Avoid round-trip losses (battery → inverter → grid → EV charger → battery in EV)
- **Cost:** Direct grid → EV charging more economical during expensive periods
- **Simplicity:** Pause discharge vs. complex battery→EV coordination

**Smart Behaviors:**

**Scenario 1: Expensive Period + EV Charging**
- **Condition:** Price in top 3 expensive periods AND EV drawing >500W
- **Behavior:** Pause battery discharge
- **Reasoning:** Battery discharge saves €0.30/kWh during expensive periods, but battery→EV transfer loses ~20% efficiency (€0.06/kWh loss). Net benefit = €0.24/kWh. BUT EV charging at €0.30/kWh is better than battery→EV at €0.36/kWh equivalent cost.

**Scenario 2: Solar + EV Charging**
- **Condition:** Solar surplus >1000W AND EV charging
- **Behavior:** Allow solar export to EV, don't trigger battery charge
- **Reasoning:** Solar → EV direct is 95% efficient vs. Solar → Battery → EV at 76% efficient (95% × 80% round-trip)

**Scenario 3: Cheap Period + EV Not Charging**
- **Condition:** Price in bottom 3 periods AND EV idle
- **Behavior:** Battery charges at 8000W, EV can charge simultaneously
- **Reasoning:** Both battery and EV benefit from cheap grid power

**Trade-offs:**
- ✅ **Pro:** Prevents inefficient energy transfers
- ✅ **Pro:** Simple pause logic (no complex coordination)
- ✅ **Pro:** Optional feature (ev_charger.enabled: false disables)
- ⚠️ **Con:** Requires EV charger sensor (sensor.ev_charger_power)
- ⚠️ **Con:** Assumes 500W threshold (may need tuning per EV model)

---

### 7. Temperature-Based Discharge Duration
**Decision:** Map outdoor temperature to discharge hours (1-3 hours) instead of fixed TopX hours

**Rationale:**
- **Heating Costs:** Cold weather = high heating costs, discharge longer to offset
- **Hot Weather:** Minimal heating, maximize discharge value
- **Seasonal Adaptation:** Automatically adjusts to weather without manual tuning

**Temperature Mapping:**
| Temperature Range | Discharge Hours | Reasoning |
|-------------------|-----------------|-----------|
| <0°C | 1 hour | Extreme cold, heating very expensive - prioritize short burst |
| 0-8°C | 1 hour | Moderate heating needs |
| 8-16°C | 2 hours | Lower heating, extend discharge |
| 16-20°C | 2 hours | Minimal heating |
| ≥20°C | 3 hours | No heating, maximize discharge value |

**Trade-offs:**
- ✅ **Pro:** Automatic seasonal adaptation
- ✅ **Pro:** Configurable thresholds (users can customize)
- ⚠️ **Con:** Assumes heating is primary load (may not suit all homes)
- ⚠️ **Con:** Outdoor temperature may not reflect indoor heating needs

---

### 8. Rank-Based Power Scaling
**Decision:** Scale discharge power based on period rank (1st most expensive = 8000W, 2nd = 6000W, 3rd = 4000W)

**Rationale:**
- **Battery Wear:** Avoid frequent low-power cycling (< 4000W)
- **Value Optimization:** More aggressive discharge during highest-value periods
- **Simplicity:** Linear scaling formula (max_power / rank)

**Formula:**
```python
discharge_power = max(max_power // rank, min_power)
```

**Examples:**
- Rank 1 (most expensive): 8000W / 1 = 8000W
- Rank 2: 8000W / 2 = 4000W (but capped at 4000W minimum)
- Rank 3: 8000W / 3 = 2666W → 4000W (minimum enforced)

**Trade-offs:**
- ✅ **Pro:** Simple formula, easy to understand
- ✅ **Pro:** Prevents battery wear from low-power cycling
- ✅ **Pro:** Maximizes value extraction from top periods
- ⚠️ **Con:** May leave value on table during rank 2+ periods (could discharge more)
- ⚠️ **Con:** Fixed minimum (4000W) may not suit all battery types

---

### 9. Graceful Degradation
**Decision:** Continue operation with reduced functionality if sensors/services unavailable

**Fallback Strategies:**

**Missing Price Data:**
- Fall back to previous day's price curve
- Log warning: "Using yesterday's prices - energy-prices add-on unavailable"

**Missing Temperature Data:**
- Use default discharge hours (2 hours)
- Log warning: "Temperature sensor unavailable, using default 2-hour discharge"

**MQTT Unavailable:**
- Log schedules only (dry-run mode)
- Retry connection every 60 seconds
- Continue monitoring SOC via HA API

**Missing EV Charger Sensor:**
- Skip EV integration checks
- Log info: "EV charger sensor unavailable, skipping EV integration"

**Rationale:**
- **Reliability:** Add-on continues working even if dependencies fail
- **Debugging:** Clear log messages indicate what's missing
- **User Experience:** Degraded operation better than complete failure

**Trade-offs:**
- ✅ **Pro:** Resilient to transient failures
- ✅ **Pro:** Clear user feedback via logs
- ⚠️ **Con:** Degraded mode may produce suboptimal schedules
- ⚠️ **Con:** Users may not notice degradation without checking logs

---

### 10. Real-Time Monitoring vs. Static Schedules
**Decision:** Hybrid approach - hourly static schedules + 1-minute real-time adjustments

**Hourly Static Schedules:**
- Run `generate_schedule()` every hour
- Analyze price curve, temperature, SOC
- Publish charge/discharge schedule to battery-api
- Battery follows schedule autonomously

**1-Minute Real-Time Monitoring:**
- Run `monitor_active_period()` every 60 seconds
- Check current SOC, grid power, solar, EV charger
- Adjust discharge if:
  - SOC drops below conservative threshold (40%)
  - Grid exporting (prevent battery→grid transfer)
  - EV charging detected (pause discharge)
  - Excess solar available (opportunistic charge)

**Rationale:**
- **Efficiency:** Hourly schedules prevent constant MQTT chatter
- **Responsiveness:** 1-minute checks catch edge cases (SOC drops, unexpected export)
- **Simplicity:** Battery-api handles execution, add-on focuses on decision-making

**Trade-offs:**
- ✅ **Pro:** Balance between static planning and dynamic adaptation
- ✅ **Pro:** Reduces MQTT traffic (hourly schedules vs. minute-by-minute commands)
- ⚠️ **Con:** 1-minute delay in responding to changes
- ⚠️ **Con:** More complex than pure static or pure dynamic approach

---

## Integration Patterns

### Home Assistant Entity Dependencies

**Required Entities:**
- `sensor.energy_prices_electricity_import_price` (from energy-prices add-on)
- `sensor.battery_api_state_of_charge` (from battery-api add-on)
- `sensor.grid_power` (from Home Assistant energy integration)

**Optional Entities:**
- `sensor.solar_power` (for opportunistic charging)
- `sensor.house_load_power` (for excess solar calculation)
- `sensor.weather_forecast_temperature` (for temperature-based discharge)
- `sensor.ev_charger_power` (for EV integration)

**Handling Missing Entities:**
```python
def get_sensor_value(ha_api, entity_id, default=None):
    """Fetch sensor value with fallback."""
    try:
        state = ha_api.get_state(entity_id)
        return float(state.get("state", default))
    except Exception as e:
        logger.warning(f"Failed to fetch {entity_id}: {e}")
        return default
```

### MQTT Topic Structure

**Schedule Publishing:**
- Topic: `battery_api/text/schedule/set`
- Payload: `{"charge": [...], "discharge": [...]}`

**Discovery Topics:**
- `homeassistant/sensor/battery_strategy_status/config`
- `homeassistant/sensor/battery_strategy_reasoning/config`
- `homeassistant/sensor/battery_strategy_forecast/config`
- `homeassistant/sensor/battery_strategy_price_ranges/config`
- `homeassistant/sensor/battery_strategy_current_action/config`

**State Topics:**
- `battery-strategy/sensor/status/state`
- `battery-strategy/sensor/reasoning/state`
- `battery-strategy/sensor/forecast/state`
- `battery-strategy/sensor/price_ranges/state`
- `battery-strategy/sensor/current_action/state`

---

## Testing Strategy

### Unit Tests (Pure Functions)
**Modules:** `price_analyzer.py`, `temperature_advisor.py`, `power_calculator.py`, `soc_guardian.py`

**Approach:**
- No mocks needed (pure functions)
- Test edge cases: empty inputs, boundary conditions, invalid inputs
- Parametric tests for temperature/rank mappings
- Target: ≥85% code coverage per module

**Example:**
```python
def test_calculate_scaled_power():
    assert calculate_scaled_power(1, 8000, 4000) == 8000
    assert calculate_scaled_power(2, 8000, 4000) == 4000
    assert calculate_scaled_power(3, 8000, 4000) == 4000
    assert calculate_scaled_power(10, 8000, 4000) == 4000
```

### Integration Tests (Sensor Readers)
**Modules:** `solar_monitor.py`, `grid_monitor.py`, `ev_charger_monitor.py`

**Approach:**
- Mock Home Assistant API responses
- Test sensor unavailable scenarios
- Test threshold detection
- Target: ≥85% code coverage per module

**Example:**
```python
def test_is_ev_charging():
    assert is_ev_charging(0, 500) == False
    assert is_ev_charging(499, 500) == False
    assert is_ev_charging(500, 500) == True
    assert is_ev_charging(7000, 500) == True
```

### End-to-End Tests (Full Flow)
**Module:** `main.py`

**Approach:**
- Mock HA API, MQTT client
- Simulate full schedule generation
- Simulate real-time monitoring loop
- Test EV integration scenarios
- Test graceful degradation (missing sensors)

**Example:**
```python
def test_generate_schedule_with_ev_charging():
    # Setup: Mock HA API with EV charging (1000W)
    # Execute: generate_schedule()
    # Assert: Discharge schedule paused for periods overlapping EV charge
```

---

## Deployment Considerations

### Resource Requirements
- **Memory:** ~50MB (Python 3.12 + dependencies)
- **CPU:** Minimal (hourly calculations, 1-min monitoring)
- **Network:** MQTT messages (~1KB/hour schedule, ~100B/min monitoring)

### Compatibility
- **Home Assistant:** ≥2024.1 (requires MQTT Discovery support)
- **Mosquitto MQTT:** Required for MQTT Discovery
- **Add-ons:** energy-prices, battery-api (dependencies)

### Migration from NetDaemonApps
1. Keep NetDaemon running during transition
2. Deploy battery-strategy with `enabled: false`
3. Compare logs for 24 hours (dry-run validation)
4. Enable battery-strategy, disable NetDaemon battery app
5. Monitor for 1 week, rollback if issues detected

---

## Future Enhancements (Not in Scope)

### Potential Improvements
- **Machine Learning:** Predict house load, optimize schedules proactively
- **Multi-Day Optimization:** Consider tomorrow's prices in today's schedule
- **Battery Health Modeling:** Adjust min/max SOC based on battery age
- **Dynamic TopX:** Adjust TopXChargeHours based on price volatility
- **Web UI:** Dashboard for visualizing schedules, reasoning, forecasts

### Why Not Now?
- **Focus on Simplicity:** Core functionality first, complexity later
- **Data Requirements:** ML needs historical data (months of logs)
- **Testing Burden:** More features = more test cases
- **User Feedback:** Validate core functionality before adding advanced features

---

**Document Status:** Complete - Ready for implementation  
**Next Step:** Begin Phase 0 (Setup & Structure)
